"""
Test saved subsection grade functionality.
"""
# pylint: disable=protected-access

import datetime

import ddt
from django.conf import settings
from django.db.utils import DatabaseError
import itertools

from mock import patch
import pytz

from capa.tests.response_xml_factory import MultipleChoiceResponseXMLFactory
from courseware.tests.helpers import get_request_for_user
from courseware.tests.test_submitting_problems import ProblemSubmissionTestMixin
from lms.djangoapps.course_blocks.api import get_course_blocks
from lms.djangoapps.grades.config.tests.utils import persistent_grades_feature_flags
from student.models import CourseEnrollment
from student.tests.factories import UserFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase, SharedModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory
from xmodule.modulestore.tests.utils import TEST_DATA_DIR
from xmodule.modulestore.xml_importer import import_course_from_xml

from ..models import PersistentSubsectionGrade
from ..new.course_grade import CourseGradeFactory
from ..new.subsection_grade import SubsectionGrade, SubsectionGradeFactory
from .utils import mock_get_score, mock_get_submissions_score


class GradeTestBase(SharedModuleStoreTestCase):
    """
    Base class for Course- and SubsectionGradeFactory tests.
    """
    @classmethod
    def setUpClass(cls):
        super(GradeTestBase, cls).setUpClass()
        cls.course = CourseFactory.create()
        cls.chapter = ItemFactory.create(
            parent=cls.course,
            category="chapter",
            display_name="Test Chapter"
        )
        cls.sequence = ItemFactory.create(
            parent=cls.chapter,
            category='sequential',
            display_name="Test Sequential 1",
            graded=True
        )
        cls.vertical = ItemFactory.create(
            parent=cls.sequence,
            category='vertical',
            display_name='Test Vertical 1'
        )
        problem_xml = MultipleChoiceResponseXMLFactory().build_xml(
            question_text='The correct answer is Choice 3',
            choices=[False, False, True, False],
            choice_names=['choice_0', 'choice_1', 'choice_2', 'choice_3']
        )
        cls.problem = ItemFactory.create(
            parent=cls.vertical,
            category="problem",
            display_name="Test Problem",
            data=problem_xml
        )

    def setUp(self):
        super(GradeTestBase, self).setUp()
        self.request = get_request_for_user(UserFactory())
        self.client.login(username=self.request.user.username, password="test")
        self.course_structure = get_course_blocks(self.request.user, self.course.location)
        self.subsection_grade_factory = SubsectionGradeFactory(self.request.user, self.course, self.course_structure)
        CourseEnrollment.enroll(self.request.user, self.course.id)


@ddt.ddt
class TestCourseGradeFactory(GradeTestBase):
    """
    Test that CourseGrades are calculated properly
    """

    @patch.dict(settings.FEATURES, {'PERSISTENT_GRADES_ENABLED_FOR_ALL_TESTS': False})
    @ddt.data(
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    )
    @ddt.unpack
    def test_course_grade_feature_gating(self, feature_flag, course_setting):
        # Grades are only saved if the feature flag and the advanced setting are
        # both set to True.
        grade_factory = CourseGradeFactory(self.request.user)
        with persistent_grades_feature_flags(
            global_flag=feature_flag,
            enabled_for_all_courses=False,
            course_id=self.course.id,
            enabled_for_course=course_setting
        ):
            with patch('lms.djangoapps.grades.new.course_grade._pretend_to_save_course_grades') as mock_save_grades:
                grade_factory.create(self.course)
        self.assertEqual(mock_save_grades.called, feature_flag and course_setting)


@ddt.ddt
class TestSubsectionGradeFactory(GradeTestBase, ProblemSubmissionTestMixin):
    """
    Tests for SubsectionGradeFactory functionality.

    Ensures that SubsectionGrades are created and updated properly, that
    persistent grades are functioning as expected, and that the flag to
    enable saving subsection grades blocks/enables that feature as expected.
    """

    def assert_grade(self, grade, expected_earned, expected_possible):
        """
        Asserts that the given grade object has the expected score.
        """
        self.assertEqual(
            (grade.all_total.earned, grade.all_total.possible),
            (expected_earned, expected_possible),
        )

    def test_create(self):
        """
        Assuming the underlying score reporting methods work,
        test that the score is calculated properly.
        """
        with mock_get_score(1, 2):
            grade = self.subsection_grade_factory.create(self.sequence)
        self.assert_grade(grade, 1, 2)

    def test_create_internals(self):
        """
        Tests to ensure that a persistent subsection grade is
        created, saved, then fetched on re-request.
        """
        with patch(
            'lms.djangoapps.grades.new.subsection_grade.PersistentSubsectionGrade.create_grade',
            wraps=PersistentSubsectionGrade.create_grade
        ) as mock_create_grade:
            with patch(
                'lms.djangoapps.grades.new.subsection_grade.SubsectionGradeFactory._get_bulk_cached_grade',
                wraps=self.subsection_grade_factory._get_bulk_cached_grade
            ) as mock_get_saved_grade:
                with self.assertNumQueries(14):
                    grade_a = self.subsection_grade_factory.create(self.sequence)
                self.assertTrue(mock_get_saved_grade.called)
                self.assertTrue(mock_create_grade.called)

                mock_get_saved_grade.reset_mock()
                mock_create_grade.reset_mock()

                with self.assertNumQueries(0):
                    grade_b = self.subsection_grade_factory.create(self.sequence)
                self.assertTrue(mock_get_saved_grade.called)
                self.assertFalse(mock_create_grade.called)

        self.assertEqual(grade_a.url_name, grade_b.url_name)
        self.assertEqual(grade_a.all_total, grade_b.all_total)

    def test_update(self):
        """
        Assuming the underlying score reporting methods work,
        test that the score is calculated properly.
        """
        with mock_get_score(1, 2):
            grade = self.subsection_grade_factory.update(self.sequence)
        self.assert_grade(grade, 1, 2)

    def test_update_if_higher(self):
        def verify_update_if_higher(mock_score, expected_grade):
            """
            Updates the subsection grade and verifies the
            resulting grade is as expected.
            """
            with mock_get_score(*mock_score):
                grade = self.subsection_grade_factory.update(self.sequence, only_if_higher=True)
                self.assert_grade(grade, *expected_grade)

        verify_update_if_higher((1, 2), (1, 2))  # previous value was non-existent
        verify_update_if_higher((2, 4), (1, 2))  # previous value was equivalent
        verify_update_if_higher((1, 4), (1, 2))  # previous value was greater
        verify_update_if_higher((3, 4), (3, 4))  # previous value was less

    @ddt.data(
        (
            'lms.djangoapps.grades.new.subsection_grade.SubsectionGrade.create_model',
            lambda self: self.subsection_grade_factory.create(self.sequence)
        ),
        (
            'lms.djangoapps.grades.new.subsection_grade.SubsectionGrade.bulk_create_models',
            lambda self: self.subsection_grade_factory.bulk_create_unsaved()
        ),
    )
    @ddt.unpack
    def test_fallback_handling(self, underlying_method, method_to_test):
        """
        Tests that the persistent grades fallback handler functions as expected.
        """
        with patch('lms.djangoapps.grades.new.subsection_grade.log') as log_mock:
            with patch(underlying_method) as underlying:
                underlying.side_effect = DatabaseError("I'm afraid I can't do that")
                method_to_test(self)
                # By making it this far, we implicitly assert
                # "the factory method swallowed the exception correctly"
                self.assertTrue(
                    log_mock.warning.call_args_list[0].startswith("Persistent Grades: Persistence Error, falling back.")
                )

    @patch.dict(settings.FEATURES, {'PERSISTENT_GRADES_ENABLED_FOR_ALL_TESTS': False})
    @ddt.data(
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    )
    @ddt.unpack
    def test_subsection_grade_feature_gating(self, feature_flag, course_setting):
        # Grades are only saved if the feature flag and the advanced setting are
        # both set to True.
        with patch(
            'lms.djangoapps.grades.models.PersistentSubsectionGrade.bulk_read_grades'
        ) as mock_read_saved_grade:
            with persistent_grades_feature_flags(
                global_flag=feature_flag,
                enabled_for_all_courses=False,
                course_id=self.course.id,
                enabled_for_course=course_setting
            ):
                self.subsection_grade_factory.create(self.sequence)
        self.assertEqual(mock_read_saved_grade.called, feature_flag and course_setting)


class SubsectionGradeTest(GradeTestBase):
    """
    Tests SubsectionGrade functionality.
    """

    def test_save_and_load(self):
        """
        Test that grades are persisted to the database properly,
        and that loading saved grades returns the same data.
        """
        # Create a grade that *isn't* saved to the database
        input_grade = SubsectionGrade(self.sequence, self.course)
        input_grade.init_from_structure(
            self.request.user,
            self.course_structure,
            self.subsection_grade_factory._submissions_scores,
            self.subsection_grade_factory._csm_scores,
        )
        self.assertEqual(PersistentSubsectionGrade.objects.count(), 0)

        # save to db, and verify object is in database
        input_grade.create_model(self.request.user)
        self.assertEqual(PersistentSubsectionGrade.objects.count(), 1)

        # load from db, and ensure output matches input
        loaded_grade = SubsectionGrade(self.sequence, self.course)
        saved_model = PersistentSubsectionGrade.read_grade(
            user_id=self.request.user.id,
            usage_key=self.sequence.location,
        )
        loaded_grade.init_from_model(
            self.request.user,
            saved_model,
            self.course_structure,
            self.subsection_grade_factory._submissions_scores,
            self.subsection_grade_factory._csm_scores,
        )

        self.assertEqual(input_grade.url_name, loaded_grade.url_name)
        self.assertEqual(input_grade.all_total, loaded_grade.all_total)


@ddt.ddt
class TestMultipleProblemTypesSubsectionScores(SharedModuleStoreTestCase):
    """
    Test grading of different problem types.
    """

    SCORED_BLOCK_COUNT = 7
    ACTUAL_TOTAL_POSSIBLE = 16.0

    @classmethod
    def setUpClass(cls):
        super(TestMultipleProblemTypesSubsectionScores, cls).setUpClass()
        cls.load_scoreable_course()
        chapter1 = cls.course.get_children()[0]
        cls.seq1 = chapter1.get_children()[0]

    def setUp(self):
        super(TestMultipleProblemTypesSubsectionScores, self).setUp()
        password = u'test'
        self.student = UserFactory.create(is_staff=False, username=u'test_student', password=password)
        self.client.login(username=self.student.username, password=password)
        self.request = get_request_for_user(self.student)
        self.course_structure = get_course_blocks(self.student, self.course.location)

    @classmethod
    def load_scoreable_course(cls):
        """
        This test course lives at `common/test/data/scoreable`.

        For details on the contents and structure of the file, see
        `common/test/data/scoreable/README`.
        """

        course_items = import_course_from_xml(
            cls.store,
            'test_user',
            TEST_DATA_DIR,
            source_dirs=['scoreable'],
            static_content_store=None,
            target_id=cls.store.make_course_key('edX', 'scoreable', '3000'),
            raise_on_failure=True,
            create_if_not_present=True,
        )

        cls.course = course_items[0]

    def test_score_submission_for_all_problems(self):
        subsection_factory = SubsectionGradeFactory(
            self.student,
            course_structure=self.course_structure,
            course=self.course,
        )
        score = subsection_factory.create(self.seq1)

        self.assertEqual(score.all_total.earned, 0.0)
        self.assertEqual(score.all_total.possible, self.ACTUAL_TOTAL_POSSIBLE)

        # Choose arbitrary, non-default values for earned and possible.
        earned_per_block = 3.0
        possible_per_block = 7.0
        with mock_get_submissions_score(earned_per_block, possible_per_block) as mock_score:
            # Configure one block to return no possible score, the rest to return 3.0 earned / 7.0 possible
            block_count = self.SCORED_BLOCK_COUNT - 1
            mock_score.side_effect = itertools.chain(
                [(earned_per_block, None, earned_per_block, None)],
                itertools.repeat(mock_score.return_value)
            )
            score = subsection_factory.update(self.seq1)
        self.assertEqual(score.all_total.earned, earned_per_block * block_count)
        self.assertEqual(score.all_total.possible, possible_per_block * block_count)


@ddt.ddt
class TestVariedMetadata(ProblemSubmissionTestMixin, ModuleStoreTestCase):
    """
    Test that changing the metadata on a block has the desired effect on the
    persisted score.
    """
    default_problem_metadata = {
        u'graded': True,
        u'weight': 2.5,
        u'due': datetime.datetime(2099, 3, 15, 12, 30, 0, tzinfo=pytz.utc),
    }

    def setUp(self):
        super(TestVariedMetadata, self).setUp()
        self.course = CourseFactory.create()
        self.chapter = ItemFactory.create(
            parent=self.course,
            category="chapter",
            display_name="Test Chapter"
        )
        self.sequence = ItemFactory.create(
            parent=self.chapter,
            category='sequential',
            display_name="Test Sequential 1",
            graded=True
        )
        self.vertical = ItemFactory.create(
            parent=self.sequence,
            category='vertical',
            display_name='Test Vertical 1'
        )
        self.problem_xml = u'''
            <problem url_name="capa-optionresponse">
              <optionresponse>
                <optioninput options="('Correct', 'Incorrect')" correct="Correct"></optioninput>
                <optioninput options="('Correct', 'Incorrect')" correct="Correct"></optioninput>
              </optionresponse>
            </problem>
        '''
        self.request = get_request_for_user(UserFactory())
        self.client.login(username=self.request.user.username, password="test")
        CourseEnrollment.enroll(self.request.user, self.course.id)
        course_structure = get_course_blocks(self.request.user, self.course.location)
        self.subsection_factory = SubsectionGradeFactory(
            self.request.user,
            course_structure=course_structure,
            course=self.course,
        )

    def _get_altered_metadata(self, alterations):
        """
        Returns a copy of the default_problem_metadata dict updated with the
        specified alterations.
        """
        metadata = self.default_problem_metadata.copy()
        metadata.update(alterations)
        return metadata

    def _add_problem_with_alterations(self, alterations):
        """
        Add a problem to the course with the specified metadata alterations.
        """

        metadata = self._get_altered_metadata(alterations)
        ItemFactory.create(
            parent=self.vertical,
            category="problem",
            display_name="problem",
            data=self.problem_xml,
            metadata=metadata,
        )

    def _get_score(self):
        """
        Return the score of the test problem when one correct problem (out of
        two) is submitted.
        """

        self.submit_question_answer(u'problem', {u'2_1': u'Correct'})
        return self.subsection_factory.create(self.sequence)

    @ddt.data(
        ({}, 1.25, 2.5),
        ({u'weight': 27}, 13.5, 27),
        ({u'weight': 1.0}, 0.5, 1.0),
        ({u'weight': 0.0}, 0.0, 0.0),
        ({u'weight': None}, 1.0, 2.0),
    )
    @ddt.unpack
    def test_weight_metadata_alterations(self, alterations, expected_earned, expected_possible):
        self._add_problem_with_alterations(alterations)
        score = self._get_score()
        self.assertEqual(score.all_total.earned, expected_earned)
        self.assertEqual(score.all_total.possible, expected_possible)

    @ddt.data(
        ({u'graded': True}, 1.25, 2.5),
        ({u'graded': False}, 0.0, 0.0),
    )
    @ddt.unpack
    def test_graded_metadata_alterations(self, alterations, expected_earned, expected_possible):
        self._add_problem_with_alterations(alterations)
        score = self._get_score()
        self.assertEqual(score.graded_total.earned, expected_earned)
        self.assertEqual(score.graded_total.possible, expected_possible)


class TestCourseGradeLogging(SharedModuleStoreTestCase):
    """
    Tests logging in the course grades module.
    Uses a larger course structure than other
    unit tests.
    """
    def setUp(self):
        super(TestCourseGradeLogging, self).setUp()
        self.course = CourseFactory.create()
        self.chapter = ItemFactory.create(
            parent=self.course,
            category="chapter",
            display_name="Test Chapter"
        )
        self.sequence = ItemFactory.create(
            parent=self.chapter,
            category='sequential',
            display_name="Test Sequential 1",
            graded=True
        )
        self.sequence_2 = ItemFactory.create(
            parent=self.chapter,
            category='sequential',
            display_name="Test Sequential 2",
            graded=True
        )
        self.sequence_3 = ItemFactory.create(
            parent=self.chapter,
            category='sequential',
            display_name="Test Sequential 3",
            graded=False
        )
        self.vertical = ItemFactory.create(
            parent=self.sequence,
            category='vertical',
            display_name='Test Vertical 1'
        )
        self.vertical_2 = ItemFactory.create(
            parent=self.sequence_2,
            category='vertical',
            display_name='Test Vertical 2'
        )
        self.vertical_3 = ItemFactory.create(
            parent=self.sequence_3,
            category='vertical',
            display_name='Test Vertical 3'
        )
        problem_xml = MultipleChoiceResponseXMLFactory().build_xml(
            question_text='The correct answer is Choice 3',
            choices=[False, False, True, False],
            choice_names=['choice_0', 'choice_1', 'choice_2', 'choice_3']
        )
        self.problem = ItemFactory.create(
            parent=self.vertical,
            category="problem",
            display_name="Test Problem 1",
            data=problem_xml
        )
        self.problem_2 = ItemFactory.create(
            parent=self.vertical_2,
            category="problem",
            display_name="Test Problem 2",
            data=problem_xml
        )
        self.problem_3 = ItemFactory.create(
            parent=self.vertical_3,
            category="problem",
            display_name="Test Problem 3",
            data=problem_xml
        )
        self.request = get_request_for_user(UserFactory())
        self.client.login(username=self.request.user.username, password="test")
        self.course_structure = get_course_blocks(self.request.user, self.course.location)
        self.subsection_grade_factory = SubsectionGradeFactory(self.request.user, self.course, self.course_structure)
        CourseEnrollment.enroll(self.request.user, self.course.id)

    def _create_course_grade_and_check_logging(
            self,
            factory,
            log_mock,
            read_only,
            subsections_read,
            subsections_created,
            blocks_accessed,
            total_graded_subsections
    ):
        """
        Creates a course grade and asserts that the associated logging
        matches the expected totals passed in to the function.
        """
        factory.create(self.course)
        log_statement = u''.join((
            u"compute_and_update, read_only: {0}, subsections read/created: {1}/{2}, blocks ",
            u"accessed: {3}, total graded subsections: {4}"
        )).format(
            read_only,
            subsections_read,
            subsections_created,
            blocks_accessed,
            total_graded_subsections,
        )
        log_mock.warning.assert_called_with(
            u"Persistent Grades: CourseGrade.{0}, course: {1}, user: {2}".format(
                log_statement,
                unicode(self.course.id),
                unicode(self.request.user.id),
            )
        )

    def test_course_grade_logging(self):
        grade_factory = CourseGradeFactory(self.request.user)
        with persistent_grades_feature_flags(
            global_flag=True,
            enabled_for_all_courses=False,
            course_id=self.course.id,
            enabled_for_course=True
        ):
            with patch('lms.djangoapps.grades.new.course_grade.log') as log_mock:
                # TODO: once merged with the "glue code" PR, update expected logging to include the relevant new info
                # the course grade has not been created, so we expect each grade to be created
                self._create_course_grade_and_check_logging(
                    grade_factory,
                    log_mock,
                    read_only=False,
                    subsections_read=0,
                    subsections_created=3,
                    blocks_accessed=3,
                    total_graded_subsections=2)
                # the course grade has been created, so we expect each grade to be read
                self._create_course_grade_and_check_logging(
                    grade_factory,
                    log_mock,
                    read_only=False,
                    subsections_read=3,
                    subsections_created=0,
                    blocks_accessed=3,
                    total_graded_subsections=2,
                )
