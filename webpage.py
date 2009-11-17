# -*- coding: UTF-8 -*-
# Copyright (C) 2006-2007 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2006-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2007 Nicolas Deram <nicolas@itaapy.com>
# Copyright (C) 2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 Sylvain Taverne <sylvain@itaapy.com>
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

# Import from standard Library
from copy import deepcopy

# Import from itools
from itools.gettext import MSG
from itools.html import xhtml_uri, XHTMLFile
from itools.http import get_context
from itools.stl import set_prefix
from itools.uri import get_reference
from itools.web import BaseView
from itools.xml import START_ELEMENT

# Import from ikaaro
import messages
from fields import RTEField
from file_views import File_Edit
from multilingual import Multilingual
from text import Text
from registry import register_resource_class
from resource_ import DBResource


def _get_links(base, events):
    map = {'a': 'href', 'img': 'src', 'iframe': 'src'}

    links = []
    for event, value, line in events:
        if event != START_ELEMENT:
            continue
        tag_uri, tag_name, attributes = value
        if tag_uri != xhtml_uri:
            continue

        # Get the attribute name and value
        attr_name = map.get(tag_name)
        if attr_name is None:
            continue

        attr_name = (None, attr_name)
        value = attributes.get(attr_name)
        if value is None:
            continue

        reference = get_reference(value)

        # Skip empty links, external links and links to '/ui/'
        if reference.scheme or reference.authority:
            continue
        path = reference.path
        if not path or path.is_absolute() and path[0] == 'ui':
            continue

        # Strip the view
        name = path.get_name()
        if name and name[0] == ';':
            path = path[:-1]

        uri = base.resolve2(path)
        uri = str(uri)
        links.append(uri)
    return links


def _change_link(source, target, base, stream):
    map = {'a': 'href', 'img': 'src', 'iframe': 'src'}

    for event in stream:
        # Process only elements of the XHTML namespace
        type, value, line = event
        if type != START_ELEMENT:
            yield event
            continue
        tag_uri, tag_name, attributes = value
        if tag_uri != xhtml_uri:
            yield event
            continue

        # Get the attribute name and value
        attr_name = map.get(tag_name)
        if attr_name is None:
            yield event
            continue

        attr_name = (None, attr_name)
        value = attributes.get(attr_name)
        if value is None:
            yield event
            continue

        reference = get_reference(value)

        # Skip empty links, external links and links to '/ui/'
        if reference.scheme or reference.authority:
            yield event
            continue
        path = reference.path
        if not path or path.is_absolute() and path[0] == 'ui':
            yield event
            continue

        # Strip the view
        name = path.get_name()
        if name and name[0] == ';':
            view = '/' + name
            path = path[:-1]
        else:
            view = ''

        # Check the link points to the resource that is moving
        path = base.resolve2(path)
        if path != source:
            yield event
            continue

        # Update the link
        # Build the new reference with the right path
        new_reference = deepcopy(reference)
        new_reference.path = str(base.get_pathto(target)) + view

        attributes[attr_name] = str(new_reference)
        yield START_ELEMENT, (tag_uri, tag_name, attributes), line


###########################################################################
# Views
###########################################################################
class WebPage_View(BaseView):
    access = 'is_allowed_to_view'
    view_title = MSG(u'View')
    icon = 'view.png'


    def http_get(self):
        body = self.resource.get_html_data()
        self.context.ok_wrap('text/html', body)



class HTMLEditView(File_Edit):
    """WYSIWYG editor for HTML documents.
    """

    data = RTEField('data', title=MSG(u'Body'))
    field_names = ['title', 'data', 'file', 'description', 'subject']


    def get_value(self, field):
        if field.name == 'data':
            return self.resource.get_html_data(language=self.content_language)

        return super(HTMLEditView, self).get_value(field)


    def action(self):
        context = self.context

        super(HTMLEditView, self).action()
        if context.edit_conflict:
            return

        # Properties
        if self.file.value is None:
            handler = self.resource.get_handler(language=self.content_language)
            handler.set_body(self.data.value)

        # Ok
        context.message = messages.MSG_CHANGES_SAVED
        context.redirect()



###########################################################################
# Model
###########################################################################
class ResourceWithHTML(object):
    """A mixin class for handlers implementing HTML editing.
    """

    edit = HTMLEditView()


    def get_html_document(self, language=None):
        # Implement it in your editable handler
        raise NotImplementedError


    def get_html_data(self, language=None):
        document = self.get_html_document(language=language)
        body = document.get_body()
        if body is None:
            return None
        return body.get_content_elements()




class WebPage(ResourceWithHTML, Multilingual, Text):

    class_id = 'webpage'
    class_title = MSG(u'Web Page')
    class_description = MSG(u'Create and publish a Web Page.')
    class_icon16 = 'icons/16x16/html.png'
    class_icon48 = 'icons/48x48/html.png'
    class_views = ['view', 'edit', 'externaledit', 'backlinks', 'edit_state',
                   'last_changes']
    class_handler = XHTMLFile


    # FIXME These three methods are private, add the heading underscore
    def get_links(self):
        base = self.get_physical_path()
        languages = self.get_site_root().get_value('website_languages')
        links = []
        for language in languages:
            handler = self.get_handler(language=language)
            links.extend(_get_links(base, handler.events))
        return links


    def update_links(self,  source, target):
        base = self.get_abspath()
        for handler in self.get_handlers():
            events = _change_link(source, target, base, handler.events)
            events = list(events)
            handler.set_changed()
            handler.events = events
        get_context().change_resource(self)


    def update_relative_links(self, source):
        target = self.get_abspath()
        prefix = target.get_pathto(source)
        # Append slash, because 'get_pathto' is the inverse of 'resolve2',
        # while 'set_prefix' uses 'resolve'
        prefix.endswith_slash = True

        for handler in self.get_handlers():
            if handler.database.is_phantom(handler):
                continue
            events = set_prefix(handler.events, prefix)
            events = list(events)
            handler.set_changed()
            handler.events = events


    #######################################################################
    # API
    #######################################################################
    def get_text(self, language=None):
        handler = self.get_handler(language=language)
        return handler.to_text()


    def get_content_type(self):
        return 'application/xhtml+xml; charset=UTF-8'


    #######################################################################
    # UI
    #######################################################################
    new_instance = DBResource.new_instance
    view = WebPage_View()

    def get_html_document(self, language=None):
        return self.get_handler(language=language)


    #######################################################################
    # Update
    #######################################################################
    def update_20080902(self):
        def fix_links(stream):
            for event in stream:
                type, value, line = event
                if type != START_ELEMENT:
                    yield event
                    continue
                tag_uri, tag_name, attributes = value
                if tag_uri != xhtml_uri:
                    yield event
                    continue
                if tag_name != 'img':
                    yield event
                    continue
                value = attributes.get((None, 'src'))
                if value is None:
                    yield event
                    continue
                uri = get_reference(value)
                if uri.scheme or uri.authority or not uri.path:
                    yield event
                    continue
                if value.startswith('/ui/'):
                    yield event
                    continue
                if str(uri.path[-1]).startswith(';'):
                    yield event
                    continue
                # Fix link
                uri = uri.resolve_name(';download')
                attributes = attributes.copy()
                attributes[(None, 'src')] = str(uri)
                yield START_ELEMENT, (tag_uri, tag_name, attributes), line

        languages = self.get_site_root().get_value('website_languages')
        for language in languages:
            handler = self.get_handler(language=language)
            events = list(fix_links(handler.events))
            handler.set_changed()
            handler.events = events



###########################################################################
# Register
###########################################################################
register_resource_class(WebPage, format='application/xhtml+xml')
