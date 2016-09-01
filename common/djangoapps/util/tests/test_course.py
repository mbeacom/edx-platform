"""
Tests for course utils.
"""
from django.core.cache import cache

import httpretty
import mock
from openedx.core.djangolib.testing.utils import CacheIsolationTestCase
from openedx.core.djangoapps.catalog.tests.mixins import CatalogIntegrationMixin
from student.tests.factories import UserFactory
from util.course import get_link_for_about_page


@httpretty.activate
class CourseAboutLinkTestCase(CatalogIntegrationMixin, CacheIsolationTestCase):
    """
    Tests for Course About link.
    """

    ENABLED_CACHES = ['default']

    def setUp(self):
        super(CourseAboutLinkTestCase, self).setUp()
        self.user = UserFactory.create(password="password")
        self.catalog_integration = self.create_catalog_integration()
        self.course_key = 'foo/bar/baz'

    def test_about_page_lms(self):
        """
        Get URL for about page, no marketing site.
        """
        with mock.patch.dict('django.conf.settings.FEATURES', {'ENABLE_MKTG_SITE': False}):
            self.assertEquals(
                get_link_for_about_page(self.course_key, self.user), "http://localhost:8000/courses/foo/bar/baz/about"
            )
        with mock.patch.dict('django.conf.settings.FEATURES', {'ENABLE_MKTG_SITE': True}):
            self.register_catalog_course_run_response(
                self.course_key, [{"key": self.course_key, "marketing_url": None}]
            )
            self.assertEquals(
                get_link_for_about_page(self.course_key, self.user), "http://localhost:8000/courses/foo/bar/baz/about"
            )

    @mock.patch.dict('django.conf.settings.FEATURES', {'ENABLE_MKTG_SITE': True})
    def test_about_page_marketing_site(self):
        """
        Get URL for about page, marketing site enabled.
        """
        self.register_catalog_course_run_response(
            [self.course_key],
            [{"key": self.course_key, "marketing_url": "https://marketing-url/course/course-title-foo-bar-baz"}]
        )
        self.assertEquals(
            get_link_for_about_page(self.course_key, self.user),
            "https://marketing-url/course/course-title-foo-bar-baz"
        )
        cached_data = cache.get_many([self.course_key])
        self.assertIn(self.course_key, cached_data.keys())

        with mock.patch('openedx.core.djangoapps.catalog.utils.get_edx_api_data') as mock_method:
            self.assertEquals(
                get_link_for_about_page(self.course_key, self.user),
                "https://marketing-url/course/course-title-foo-bar-baz"
            )
            self.assertEqual(0, mock_method.call_count)
