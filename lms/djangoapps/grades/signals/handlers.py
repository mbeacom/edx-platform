"""
Grades related signals.
"""

from celery import Task
from django.dispatch import receiver
from logging import getLogger

from courseware.model_data import get_score, set_score
from openedx.core.lib.grade_utils import is_score_higher
from student.models import user_by_anonymous_id
from submissions.models import score_set, score_reset

from .signals import COURSE_GRADE_UPDATE_REQUESTED, SCORE_CHANGED, SCORE_PUBLISHED
from ..tasks import recalculate_subsection_grade, recalculate_course_grade


log = getLogger(__name__)


@receiver(score_set)
def submissions_score_set_handler(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Consume the score_set signal defined in the Submissions API, and convert it
    to a SCORE_CHANGED signal defined in this module. Converts the unicode keys
    for user, course and item into the standard representation for the
    SCORE_CHANGED signal.

    This method expects that the kwargs dictionary will contain the following
    entries (See the definition of score_set):
      - 'points_possible': integer,
      - 'points_earned': integer,
      - 'anonymous_user_id': unicode,
      - 'course_id': unicode,
      - 'item_id': unicode
    """
    points_possible = kwargs['points_possible']
    points_earned = kwargs['points_earned']
    course_id = kwargs['course_id']
    usage_id = kwargs['item_id']
    user = user_by_anonymous_id(kwargs['anonymous_user_id'])
    if user is None:
        return

    SCORE_CHANGED.send(
        sender=None,
        points_earned=points_earned,
        points_possible=points_possible,
        user_id=user.id,
        course_id=course_id,
        usage_id=usage_id
    )


@receiver(score_reset)
def submissions_score_reset_handler(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Consume the score_reset signal defined in the Submissions API, and convert
    it to a SCORE_CHANGED signal indicating that the score has been set to 0/0.
    Converts the unicode keys for user, course and item into the standard
    representation for the SCORE_CHANGED signal.

    This method expects that the kwargs dictionary will contain the following
    entries (See the definition of score_reset):
      - 'anonymous_user_id': unicode,
      - 'course_id': unicode,
      - 'item_id': unicode
    """
    course_id = kwargs['course_id']
    usage_id = kwargs['item_id']
    user = user_by_anonymous_id(kwargs['anonymous_user_id'])
    if user is None:
        return

    SCORE_CHANGED.send(
        sender=None,
        points_earned=0,
        points_possible=0,
        user_id=user.id,
        course_id=course_id,
        usage_id=usage_id
    )


@receiver(SCORE_PUBLISHED)
def score_published_handler(sender, block, user, raw_earned, raw_possible, only_if_higher, **kwargs):  # pylint: disable=unused-argument
    """
    Handles whenever a block's score is published.
    Returns whether the score was actually updated.
    """
    update_score = True
    if only_if_higher:
        previous_score = get_score(user.id, block.location)

        if previous_score:
            prev_raw_earned, prev_raw_possible = previous_score  # pylint: disable=unpacking-non-sequence

            if not is_score_higher(prev_raw_earned, prev_raw_possible, raw_earned, raw_possible):
                update_score = False
                log.warning(
                    u"Grades: Rescore is not higher than previous: "
                    u"user: {}, block: {}, previous: {}/{}, new: {}/{} ".format(
                        user, block.location, prev_raw_earned, prev_raw_possible, raw_earned, raw_possible,
                    )
                )

    if update_score:
        set_score(user.id, block.location, raw_earned, raw_possible)

        SCORE_CHANGED.send(
            sender=None,
            points_earned=raw_earned,
            points_possible=raw_possible,
            user_id=user.id,
            course_id=unicode(block.location.course_key),
            usage_id=unicode(block.location),
            only_if_higher=only_if_higher,
        )
    return update_score


@receiver(SCORE_CHANGED)
def enqueue_subsection_update(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Handles the SCORE_CHANGED signal by enqueueing a subsection update operation to occur asynchronously.
    """
    recalculate_subsection_grade.apply_async(
        args=(
            kwargs['user_id'],
            kwargs['course_id'],
            kwargs['usage_id'],
            kwargs.get('only_if_higher'),
        )
    )


@receiver(COURSE_GRADE_UPDATE_REQUESTED)
def enqueue_course_update(sender, **kwargs):  # pylint: disable=unused-argument
    """
    Handles the COURSE_GRADE_UPDATE_REQUESTED signal by enqueueing a course update operation to occur asynchronously.
    """
    if isinstance(sender, Task):  # We're already in a async worker, just do the task
        recalculate_course_grade.apply(args=(kwargs['user_id'], kwargs['course_id']))
    else:  # Otherwise, queue the work to be done asynchronously
        recalculate_course_grade.apply_async(args=(kwargs['user_id'], kwargs['course_id']))
