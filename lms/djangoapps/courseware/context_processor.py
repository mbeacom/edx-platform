"""
This is the courseware context_processor module.

This is meant to simplify the process of sending user preferences (espec. time_zone and pref-lang)
to the templates without having to append every view file.

"""
from openedx.core.djangoapps.user_api.preferences.api import get_user_preference
LANGUAGE_KEY = 'pref-lang'

def user_timezone_locale_prefs(request):
    """
    Checks if request has an authenticated user.
    If so, sends set (or none if unset) time_zone and language prefs.

    This interacts with the DateUtils to either display preferred or attempt to determine
    system/browser set time_zones and languages

    """
    if request.user.is_authenticated():
        return {
            'user_timezone': request.user.preferences.model.get_value(request.user, "time_zone"),
            'user_language': get_user_preference(request.user, LANGUAGE_KEY)
        }
    else:
        return {
            'user_timezone': None,
            'user_language': None
        }
