from datetime import datetime
from couchdbkit.ext.django.schema import *
from couchdbkit.exceptions import ResourceNotFound
from django.conf import settings
from django.contrib.auth.models import get_hexdigest, check_password, UNUSABLE_PASSWORD
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
import random

from . import app_label


class SiteProfileNotAvailable(Exception):
    pass


class User(Document):
    username      = StringProperty(required=True)
    first_name    = StringProperty(required=False)
    last_name     = StringProperty(required=False)
    email         = StringProperty(required=False)
    password      = StringProperty(required=True)
    is_staff      = BooleanProperty(default=False)
    is_active     = BooleanProperty(default=True)
    is_superuser  = BooleanProperty(default=False)
    last_login    = DateTimeProperty(required=False)
    date_joined   = DateTimeProperty(default=datetime.utcnow)

    class Meta:
        app_label = app_label

    def __unicode__(self):
        return self.username

    def __repr__(self):
        return "<User: %s>" %self.username

    def is_anonymous(self):
        return False

    def save(self):
        if not self.check_username():
            raise Exception('This username is already in use.')
        if not self.check_email():
            raise Exception('This email address is already in use.')
        return super(self.__class__, self).save()


    def check_username(self):
        u = User.get_user(self.username, is_active=None)
        if u is None:
            return True
        return u._id == self._id

    def check_email(self):
        u = User.get_user_by_email(self.email, is_active=None)
        if u is None:
            return True
        return u._id == self._id

    def _get_id(self):
        return self.username

    id = property(_get_id)

    def get_full_name(self):
        "Returns the first_name plus the last_name, with a space in between."
        full_name = u'%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def is_authenticated(self):
        return True

    def set_password(self, raw_password):
        algo = 'sha1'
        salt = get_hexdigest(algo, str(random.random()), str(random.random()))[:5]
        hsh = get_hexdigest(algo, salt, raw_password)
        self.password = '%s$%s$%s' % (algo, salt, hsh)

    def check_password(self, raw_password):
        """
        Returns a boolean of whether the raw_password was correct. Handles
        encryption formats behind the scenes.
        """
        return check_password(raw_password, self.password)

    def set_unusable_password(self):
        # Sets a value that will never be a valid hash
        self.password = UNUSABLE_PASSWORD

    def has_usable_password(self):
        return self.password != UNUSABLE_PASSWORD

    def email_user(self, subject, message, from_email=None):
        "Sends an e-mail to this User."
        send_mail(subject, message, from_email, [self.email])

    def get_profile(self):
        """
        Returns site-specific profile for this user. Raises
        SiteProfileNotAvailable if this site does not allow profiles.
        """
        if not hasattr(self, '_profile_cache'):
            from django.conf import settings
            if not getattr(settings, 'AUTH_PROFILE_MODULE', False):
                raise SiteProfileNotAvailable('You need to set AUTH_PROFILE_MO'
                                              'DULE in your project settings')
            try:
                app_label, model_name = settings.AUTH_PROFILE_MODULE.split('.')
            except ValueError:
                raise SiteProfileNotAvailable('app_label and model_name should'
                        ' be separated by a dot in the AUTH_PROFILE_MODULE set'
                        'ting')

            try:
                ### model = models.get_model(app_label, model_name)
                from django.db.models.loading import get_app
                app = get_app(app_label)
                model = getattr(app, model_name, None)

                if model is None:
                    raise SiteProfileNotAvailable('Unable to load the profile '
                        'model, check AUTH_PROFILE_MODULE in your project sett'
                        'ings')
                ### self._profile_cache = model._default_manager.using(self._state.db).get(user__id__exact=self.id)
                self._profile_cache = model.get_userprofile(self.get_id)

                ### self._profile_cache.user = self
            except (ImportError, ImproperlyConfigured):
                raise SiteProfileNotAvailable
        return self._profile_cache

    def get_and_delete_messages(self):
        # Todo: Implement messaging and groups.
        return None

    @classmethod
    def get_user(cls, username, is_active=True):
        param = {"key": username}

        r = cls.view('%s/users_by_username' % cls._meta.app_label, 
                     include_docs=True, 
                     **param).first()
        if r and r.is_active:
            return r
        return None

    @classmethod
    def get_user_by_email(cls, email, is_active=True):
        param = {"key": email}

        r = cls.view('%s/users_by_email' % cls._meta.app_label, 
                     include_docs=True, **param).first()
        if r and r.is_active:
            return r
        return None

    @classmethod
    def all_users(cls):
        view = cls.view('%s/users_by_username' % cls._meta.app_label, include_docs=True)
        try:
            view.count()
            return view.iterator()
        except ResourceNotFound:
            return []


class UserProfile(Document):
    '''This is a dummy class to demonstrate the use of a UserProfile.
    It's used in tests. To use a UserProfile in your app, don't subclass this,
    define your own class, use a permanent view and set AUTH_PROFILE_MODULE in
    settings.py to point to your class.'''
    user_id = StringProperty()
    age = IntegerProperty()

    class Meta:
        app_label = app_label

    @classmethod
    def get_userprofile(cls, user_id):
        # With a permanent view:
        # r = cls.view('%s/userprofile_by_userid' % cls._meta.app_label,
        #              key=user_id, include_docs=True)

        design_doc = {
            "map": """function(doc) { if (doc.doc_type == "UserProfile") { emit(doc.user_id, doc); }}"""
        }
        r = cls.temp_view(design_doc, key=user_id)
        return r.first() if r else None
