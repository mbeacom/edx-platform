"""
Signal handlers for the gating djangoapp
"""
from django.dispatch import receiver

from gating import api as gating_api
from lms.djangoapps.grades.signals.signals import SCORE_CHANGED, SUBSECTION_SCORE_CHANGED
from opaque_keys.edx.keys import CourseKey, UsageKey
from xmodule.modulestore.django import modulestore


@receiver(SCORE_CHANGED)
def handle_score_changed(**kwargs):
    """
    Receives the SCORE_CHANGED signal sent by LMS when a student's score has changed
    for a given component and triggers the evaluation of any milestone relationships
    which are attached to the updated content.

    Arguments:
        kwargs (dict): Contains user ID, course key, and content usage key

    Returns:
        None
    """
    course = modulestore().get_course(CourseKey.from_string(kwargs.get('course_id')))
    block = modulestore().get_item(UsageKey.from_string(kwargs.get('usage_id')))
    gating_api.evaluate_entrance_exam(course, block, kwargs.get('user_id'))


@receiver(SUBSECTION_SCORE_CHANGED)
def handle_subsection_score_changed(**kwargs):
    """
    Receives the SUBSECTION_SCORE_CHANGED signal and triggers the evaluation of
    any milestone relationships which are attached to the updated content.
    Arguments:
        kwargs (dict): Contains user ID, course key, and content usage key
    Returns:
        None
    """
    course = kwargs['course']
    if course.enable_subsection_gating:
        subsection_grade = kwargs['subsection_grade']
        new_score = subsection_grade.graded_total.earned / subsection_grade.graded_total.possible * 100.0
        gating_api.evaluate_prerequisite(
            course,
            kwargs['user'],
            subsection_grade.location,
            new_score,
        )
