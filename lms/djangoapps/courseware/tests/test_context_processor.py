"""
Unit tests for courseware context_processor
"""
from django.contrib.auth.models import AnonymousUser
from mock import patch, Mock

from student.tests.factories import UserFactory
from xmodule.modulestore.tests.django_utils import ModuleStoreTestCase
from openedx.core.djangoapps.user_api.preferences.api import set_user_preference

from courseware.context_processor import user_timezone_locale_prefs


class UserPrefContextProcessorUnitTest(ModuleStoreTestCase):
    """
    Unit test for courseware context_processor
    """
    def setUp(self):
        super(UserPrefContextProcessorUnitTest, self).setUp()

        self.user = UserFactory.create()
        self.request = Mock()
        self.request.user = self.user

    def test_anonymous_user(self):
        self.request.user = AnonymousUser()
        context = user_timezone_locale_prefs(self.request)
        self.assertTrue(context['user_timezone'] is None)
        self.assertTrue(context['user_language'] is None)

    def test_no_timezone_preference(self):
        set_user_preference(self.user, 'pref-lang', 'en')
        context = user_timezone_locale_prefs(self.request)
        self.assertTrue(context['user_timezone'] is None)
        self.assertFalse(context['user_language'] is None)
        self.assertTrue(context['user_language'] == 'en')

    def test_no_language_preference(self):
        set_user_preference(self.user, 'time_zone', 'Asia/Tokyo')
        context = user_timezone_locale_prefs(self.request)
        self.assertTrue(context['user_language'] is None)
        self.assertFalse(context['user_timezone'] is None)
        self.assertTrue(context['user_timezone'] == 'Asia/Tokyo')
