"""
Tests for the functionality and infrastructure of grades tasks.
"""

from collections import OrderedDict
import ddt
from django.conf import settings
from django.db.utils import IntegrityError
from mock import patch
from unittest import skip

from student.models import anonymous_id_for_user
from student.tests.factories import UserFactory
from xmodule.modulestore import ModuleStoreEnum
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from xmodule.modulestore.tests.factories import CourseFactory, ItemFactory, check_mongo_calls

from lms.djangoapps.grades.config.models import PersistentGradesEnabledFlag
from lms.djangoapps.grades.signals.signals import COURSE_GRADE_UPDATE_REQUESTED, SCORE_CHANGED
from lms.djangoapps.grades.tasks import recalculate_course_grade, recalculate_subsection_grade


@patch.dict(settings.FEATURES, {'PERSISTENT_GRADES_ENABLED_FOR_ALL_TESTS': False})
@ddt.ddt
class RecalculateSubsectionGradeTest(ModuleStoreTestCase):
    """
    Ensures that the recalculate subsection grade task functions as expected when run.
    """
    def setUp(self):
        super(RecalculateSubsectionGradeTest, self).setUp()
        self.user = UserFactory()
        PersistentGradesEnabledFlag.objects.create(enabled_for_all_courses=True, enabled=True)

    def set_up_course(self, enable_subsection_grades=True):
        """
        Configures the course for this test.
        """
        # pylint: disable=attribute-defined-outside-init,no-member
        self.course = CourseFactory.create(
            org='edx',
            name='course',
            run='run',
        )
        if not enable_subsection_grades:
            PersistentGradesEnabledFlag.objects.create(enabled=False)

        self.chapter = ItemFactory.create(parent=self.course, category="chapter", display_name="Chapter")
        self.sequential = ItemFactory.create(parent=self.chapter, category='sequential', display_name="Open Sequential")
        self.problem = ItemFactory.create(parent=self.sequential, category='problem', display_name='problem')

        self.score_changed_kwargs = OrderedDict([
            ('user_id', self.user.id),
            ('course_id', unicode(self.course.id)),
            ('usage_id', unicode(self.problem.location)),
            ('only_if_higher', None),
        ])

        # this call caches the anonymous id on the user object, saving 4 queries in all happy path tests
        _ = anonymous_id_for_user(self.user, self.course.id)
        # pylint: enable=attribute-defined-outside-init,no-member

    @ddt.data(
        ('lms.djangoapps.grades.tasks.recalculate_subsection_grade.apply_async', SCORE_CHANGED),
        ('lms.djangoapps.grades.tasks.recalculate_course_grade.apply_async', COURSE_GRADE_UPDATE_REQUESTED)
    )
    @ddt.unpack
    def test_signal_queues_task(self, enqueue_op, test_signal):
        """
        Ensures that the SCORE_CHANGED and COURSE_GRADE_UPDATE_REQUESTED signals enqueue the correct tasks.
        """
        self.set_up_course()
        if test_signal == SCORE_CHANGED:
            expected_args = tuple(self.score_changed_kwargs.values())
        else:
            expected_args = (self.score_changed_kwargs['user_id'], self.score_changed_kwargs['course_id'])
        with patch(
            enqueue_op,
            return_value=None
        ) as mock_task_apply:
            test_signal.send(sender=None, **self.score_changed_kwargs)
            mock_task_apply.assert_called_once_with(args=expected_args)

    @patch('lms.djangoapps.grades.signals.signals.COURSE_GRADE_UPDATE_REQUESTED.send')
    def test_subsection_update_triggers_course_update(self, mock_course_signal):
        """
        Ensures that the subsection update operation also updates the course grade.
        """
        self.set_up_course()
        recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))
        mock_course_signal.assert_called_once_with(
            sender=recalculate_subsection_grade,
            course_id=self.score_changed_kwargs['course_id'],
            user_id=self.score_changed_kwargs['user_id'],
        )

    @ddt.data(True, False)
    def test_course_update_enqueuing(self, should_be_async):
        """
        Ensures that the course update operation is enqueued on an async queue (or not) as expected.
        """
        base = 'lms.djangoapps.grades.tasks.recalculate_course_grade'
        if should_be_async:
            executed = base + '.apply_async'
            other = base + '.apply'
            sender = None
        else:
            executed = base + '.apply'
            other = base + '.apply_async'
            sender = recalculate_subsection_grade
        self.set_up_course()

        with patch(executed, return_value=None) as executed_task:
            with patch(other, return_value=None) as other_task:
                COURSE_GRADE_UPDATE_REQUESTED.send(
                    sender=sender,
                    course_id=self.score_changed_kwargs['course_id'],
                    user_id=self.score_changed_kwargs['user_id'],
                )
                other_task.assert_not_called()
                executed_task.assert_called_once_with(
                    args=(
                        self.score_changed_kwargs['user_id'],
                        self.score_changed_kwargs['course_id'],
                    )
                )

    @ddt.data(
        (ModuleStoreEnum.Type.mongo, 1),
        (ModuleStoreEnum.Type.split, 0),
    )
    @ddt.unpack
    def test_subsection_grade_updated(self, default_store, added_queries):
        with self.store.default_store(default_store):
            self.set_up_course()
            self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            with check_mongo_calls(2) and self.assertNumQueries(21 + added_queries):
                recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))

    def test_single_call_to_create_block_structure(self):
        self.set_up_course()
        self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
        with patch(
            'openedx.core.lib.block_structure.factory.BlockStructureFactory.create_from_cache',
            return_value=None,
        ) as mock_block_structure_create:
            recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))
            self.assertEquals(mock_block_structure_create.call_count, 2)

    @ddt.data(
        (ModuleStoreEnum.Type.mongo, 1),
        (ModuleStoreEnum.Type.split, 0),
    )
    @ddt.unpack
    def test_query_count_does_not_change_with_more_problems(self, default_store, added_queries):
        with self.store.default_store(default_store):
            self.set_up_course()
            self.assertTrue(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            ItemFactory.create(parent=self.sequential, category='problem', display_name='problem2')
            ItemFactory.create(parent=self.sequential, category='problem', display_name='problem3')
            with check_mongo_calls(2) and self.assertNumQueries(21 + added_queries):
                recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))

    @ddt.data(ModuleStoreEnum.Type.mongo, ModuleStoreEnum.Type.split)
    def test_subsection_grades_not_enabled_on_course(self, default_store):
        with self.store.default_store(default_store):
            self.set_up_course(enable_subsection_grades=False)
            self.assertFalse(PersistentGradesEnabledFlag.feature_enabled(self.course.id))
            with check_mongo_calls(2) and self.assertNumQueries(5):
                recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))

    @skip("Pending completion of TNL-5089")
    @ddt.data(
        (ModuleStoreEnum.Type.mongo, True),
        (ModuleStoreEnum.Type.split, True),
        (ModuleStoreEnum.Type.mongo, False),
        (ModuleStoreEnum.Type.split, False),
    )
    @ddt.unpack
    def test_query_counts_with_feature_flag(self, default_store, feature_flag):
        PersistentGradesEnabledFlag.objects.create(enabled=feature_flag)
        with self.store.default_store(default_store):
            self.set_up_course()
            with check_mongo_calls(0) and self.assertNumQueries(3 if feature_flag else 2):
                recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))

    @patch('lms.djangoapps.grades.tasks.recalculate_subsection_grade.retry')
    @patch('lms.djangoapps.grades.new.subsection_grade.SubsectionGradeFactory.update')
    def test_retry_subsection_update_on_integrity_error(self, mock_update, mock_retry):
        """
        Ensures that tasks will be retried if IntegrityErrors are encountered.
        """
        self.set_up_course()
        mock_update.side_effect = IntegrityError("WHAMMY")
        recalculate_subsection_grade.apply(args=tuple(self.score_changed_kwargs.values()))
        self.assertTrue(mock_retry.called)

    @patch('lms.djangoapps.grades.tasks.recalculate_course_grade.retry')
    @patch('lms.djangoapps.grades.new.course_grade.CourseGradeFactory.update')
    def test_retry_course_update_on_integrity_error(self, mock_update, mock_retry):
        """
        Ensures that tasks will be retried if IntegrityErrors are encountered.
        """
        self.set_up_course()
        mock_update.side_effect = IntegrityError("WHAMMY")
        recalculate_course_grade.apply(
            args=(
                self.score_changed_kwargs['user_id'],
                self.score_changed_kwargs['course_id'],
            )
        )
        self.assertTrue(mock_retry.called)
