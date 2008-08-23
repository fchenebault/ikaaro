# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Henry Obein <henry@itaapy.com>
# Copyright (C) 2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007-2008 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2008 Nicolas Deram <nicolas@itaapy.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Import from the Standard Library
from decimal import Decimal
from types import GeneratorType

# Import from itools
from itools.datatypes import Tokens
from itools.gettext import MSG
from itools.html import stream_to_str_as_html
from itools.web import STLView
from itools.xml import XMLParser

# Import from ikaaro
from access import RoleAware
from folder import Folder
from registry import register_object_class
from registry import register_website
from skins import UI, ui_path
from website_views import AboutView, BrokenLinks, ContactForm
from website_views import ContactOptionsForm, ControlPanel, CreditsView
from website_views import EditLanguagesForm, ForgottenPasswordForm, LoginView
from website_views import LogoutView, NewWebSiteForm, RegisterForm
from website_views import SecurityPolicyForm, SiteSearchView, VHostsForm



class WebSite(RoleAware, Folder):

    class_id = 'WebSite'
    class_version = '20071215'
    class_title = MSG(u'Web Site')
    class_description = MSG(u'Create a new Web Site or Work Place.')
    class_icon16 = 'icons/16x16/website.png'
    class_icon48 = 'icons/48x48/website.png'
    class_skin = 'ui/aruni'
    class_views = ['browse_content', 'preview_content', 'new_resource',
                   'edit_metadata', 'control_panel', 'last_changes']
    class_control_panel = ['permissions', 'new_user', 'edit_virtual_hosts',
                           'edit_security_policy', 'edit_languages',
                           'edit_contact_options', 'broken_links', 'orphans'],


    __fixed_handlers__ = ['skin', 'index']


    def _get_resource(self, name):
        if name == 'ui':
            ui = UI(ui_path)
            ui.database = self.metadata.database
            return ui
        if name in ('users', 'users.metadata'):
            return self.parent._get_resource(name)
        return Folder._get_resource(self, name)


    @classmethod
    def get_metadata_schema(cls):
        schema = Folder.get_metadata_schema()
        schema.update(RoleAware.get_metadata_schema())
        schema['vhosts'] = Tokens(default=())
        schema['contacts'] = Tokens(default=())
        schema['website_languages'] = Tokens(default=('en',))
        return schema


    ########################################################################
    # Publish
    ########################################################################
    unauthorized = LoginView()


    ########################################################################
    # API
    ########################################################################
    def get_default_language(self):
        return self.get_property('website_languages')[0]


    def before_traverse(self, context, min=Decimal('0.000001'),
                        zero=Decimal('0.0')):
        # The default language
        accept = context.accept_language
        default = self.get_default_language()
        if accept.get(default, zero) < min:
            accept.set(default, min)
        # The Query
        language = context.get_form_value('language')
        if language is not None:
            context.set_cookie('language', language)
        # Language negotiation
        user = context.user
        if user is None:
            language = context.get_cookie('language')
            if language is not None:
                accept.set(language, 2.0)
        else:
            language = user.get_property('user_language')
            accept.set(language, 2.0)


    def after_traverse(self, context):
        body = context.entity
        if not isinstance(body, (str, list, GeneratorType, XMLParser)):
            return

        # If there is not content type and the body is not None, wrap it in
        # the skin template
        if context.response.has_header('Content-Type'):
            if isinstance(body, (list, GeneratorType, XMLParser)):
                context.entity = stream_to_str_as_html(body)
            return

        if isinstance(body, str):
            body = XMLParser(body)
        context.entity = context.root.get_skin().template(body)


    def is_allowed_to_register(self, user, object):
        return self.get_property('website_is_open')


    #######################################################################
    # UI
    #######################################################################
    new_instance = NewWebSiteForm()
    # Control Panel
    control_panel = ControlPanel()
    edit_virtual_hosts = VHostsForm()
    edit_security_policy = SecurityPolicyForm()
    edit_contact_options = ContactOptionsForm()
    edit_languages = EditLanguagesForm()
    broken_links = BrokenLinks()
    # Register / Login
    register = RegisterForm()
    login = LoginView()
    logout = LogoutView()
    forgotten_password = ForgottenPasswordForm()
    # Public views
    site_search = SiteSearchView()
    contact = ContactForm()
    about = AboutView()
    credits = CreditsView()
    license = STLView(access=True, title=MSG(u'License'),
                      template='/ui/root/license.xml')


###########################################################################
# Register
###########################################################################
register_object_class(WebSite)
register_website(WebSite)
