import os, sys
sys.path.append('/Users/aaron/Sites/mosy.com')
os.environ['DJANGO_SETTINGS_MODULE'] = 'mosy.settings'
import django.core.handlers.wsgi
application = django.core.handlers.wsgi.WSGIHandler()
