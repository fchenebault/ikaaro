# -*- coding: UTF-8 -*-
# Copyright (C) 2005-2008 Juan David Ibáñez Palomar <jdavid@itaapy.com>
# Copyright (C) 2006-2008 Hervé Cauwelier <herve@itaapy.com>
# Copyright (C) 2007 Sylvain Taverne <sylvain@itaapy.com>
# Copyright (C) 2007-2008 Henry Obein <henry@itaapy.com>
# Copyright (C) 2008 Matthieu France <matthieu@itaapy.com>
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
from datetime import datetime

# Import from itools
from itools.csv import Property
from itools.core import send_subprocess, read_subprocess
from itools.datatypes import Unicode, String, Integer, Boolean, DateTime
from itools.http import get_context
from itools.uri import Path
from itools.web import Resource
from itools.xapian import CatalogAware, PhraseQuery

# Import from ikaaro
from lock import Lock
from metadata import Metadata
from registry import register_field
from resource_views import DBResource_Edit, DBResource_Backlinks
from resource_views import DBResource_AddImage, DBResource_AddLink
from resource_views import LoginView, LogoutView
from revisions_views import DBResource_LastChanges, DBResource_Changes
from workflow import WorkflowAware
from views_new import NewInstance


class IResource(Resource):

    class_views = []
    context_menus = []


    def get_parent(self):
        # Special case: the root
        if not self.path:
            return None
        path = self.path[:-1]
        return self.context.get_resource(path)

    parent = property(get_parent, None, None, '')


    def get_name(self):
        # Special case: the root
        if not self.path:
            return None

        return self.path[-1]

    name = property(get_name, None, None, '')


    def get_site_root(self):
        from website import WebSite
        resource = self
        while not isinstance(resource, WebSite):
            resource = resource.parent
        return resource


    def get_default_view_name(self):
        views = self.class_views
        if not views:
            return None
        context = get_context()
        ac = self.get_access_control()
        for view_name in views:
            view = getattr(self, view_name, None)
            if ac.is_access_allowed(context, self, view):
                return view_name
        return views[0]


    def get_context_menus(self):
        return self.context_menus


    ########################################################################
    # Properties
    ########################################################################
    @classmethod
    def get_property_datatype(cls, name):
        return String


    def _get_property(self, name, language=None):
        return None


    def get_property(self, name, language=None):
        """Return the property value for the given property name.
        """
        property = self._get_property(name, language=language)
        # Default
        if not property:
            datatype = self.get_property_datatype(name)
            return datatype.get_default()

        # Multiple
        if type(property) is list:
            return [ x.value for x in property ]

        # Simple
        return property.value


    def get_title(self):
        return unicode(self.name)


    def get_page_title(self):
        return self.get_title()


    ########################################################################
    # Icons
    ########################################################################
    @classmethod
    def get_class_icon(cls, size=16):
        icon = getattr(cls, 'class_icon%s' % size, None)
        if icon is None:
            return None
        return '/ui/%s' % icon


    @classmethod
    def get_resource_icon(cls, size=16):
        icon = getattr(cls, 'icon%s' % size, None)
        if icon is None:
            return cls.get_class_icon(size)
        return ';icon%s' % size


    def get_method_icon(self, view, size='16x16', **kw):
        icon = getattr(view, 'icon', None)
        if icon is None:
            return None
        if callable(icon):
            icon = icon(self, **kw)
        return '/ui/icons/%s/%s' % (size, icon)


    ########################################################################
    # User interface
    ########################################################################
    def get_views(self):
        context = get_context()
        ac = self.get_access_control()
        for name in self.class_views:
            view_name = name.split('?')[0]
            view = self.get_view(view_name)
            if ac.is_access_allowed(context, self, view):
                yield name, view



class DBResource(CatalogAware, IResource):

    def __init__(self, metadata):
        self.metadata = metadata
        self._handler = None


    @staticmethod
    def make_resource(cls, container, name, *args, **kw):
        cls._make_resource(cls, container.handler, name, *args, **kw)
        resource = container.get_resource(name)
        # Events, add
        get_context().add_resource(resource)

        return resource


    @staticmethod
    def _make_resource(cls, folder, name, **kw):
        metadata = cls.build_metadata(**kw)
        folder.set_handler('%s.metadata' % name, metadata)


    def get_handler(self):
        if self._handler is None:
            cls = self.class_handler
            database = self.metadata.database
            uri = self.metadata.uri[:-len('.metadata')]
            if database.has_handler(uri):
                handler = database.get_handler(uri, cls=cls)
            else:
                handler = cls()
                database.push_handler(uri, handler)
            self._handler = handler
        return self._handler

    handler = property(get_handler, None, None, '')


    def load_handlers(self):
        self.get_handlers()


    ########################################################################
    # Metadata
    ########################################################################
    @classmethod
    def get_metadata_schema(cls):
        return {
            'version': String,
            'title': Unicode(multilingual=True),
            'description': Unicode(multilingual=True),
            'subject': Unicode(multilingual=True),
            }


    @classmethod
    def build_metadata(cls, format=None, **kw):
        """Return a Metadata object with sensible default values.
        """
        metadata = Metadata(cls=cls, format=format)
        # Properties
        for key in kw:
            value = kw[key]
            if type(value) is dict:
                for lang in value:
                    property = Property(value[lang], lang=lang)
                    metadata._set_property(key, property)
            else:
                metadata._set_property(key, value)

        # Workflow State (default)
        if kw.get('state') is None and issubclass(cls, WorkflowAware):
            schema = cls.get_metadata_schema()
            state = schema['state'].get_default()
            if state is None:
                state  = cls.workflow.initstate
            metadata._set_property('state', state)

        # Ok
        return metadata


    def has_property(self, name, language=None):
        return self.metadata.has_property(name, language=language)


    @classmethod
    def get_property_datatype(cls, name):
         schema = cls.get_metadata_schema()
         return schema.get(name, String)


    def _get_property(self, name, language=None):
        return self.metadata.get_property(name, language=language)


    def set_property(self, name, value, language=None):
        get_context().change_resource(self)
        if language:
            value = Property(value, lang=language)
        self.metadata.set_property(name, value)


    def del_property(self, name):
        get_context().server.change_resource(self)
        self.metadata.del_property(name)


    ########################################################################
    # Versioning
    ########################################################################
    def get_files_to_archive(self, content=False):
        raise NotImplementedError


    def get_revisions(self, n=None, content=False, action=0):
        # action
        # 0: normal
        # 1: call git, and come back
        # 2: read the the data from git

        if action == 0 or action == 1:
            # Make the Git command
            files = self.get_files_to_archive(content)
            cmd = ['git', 'rev-list', '--pretty=format:%an%n%at%n%s']
            if n is not None:
                cmd = cmd + ['-n', str(n)]
            cmd = cmd + ['HEAD', '--'] + files
            if action == 0:
                data = send_subprocess(cmd)
            else:
                send_subprocess(cmd, wait=False)
                return
        else:
            data = read_subprocess()

        # Parse output
        revisions = []
        lines = data.splitlines()
        for idx in range(len(lines) / 4):
            base = idx * 4
            ts = int(lines[base+2])
            revisions.append(
                {'revision': lines[base].split()[1], # commit
                 'username': lines[base+1],          # author name
                 'date': datetime.fromtimestamp(ts), # author date
                 'message': lines[base+3],           # subject
                })
        # Ok
        return revisions


    def get_owner(self):
        revisions = self.get_revisions()
        if not revisions:
            return None
        return revisions[-1]['username']


    def get_last_author(self):
        revisions = self.get_revisions(1)
        if not revisions:
            return None
        return revisions[0]['username']


    def get_mtime(self):
        revisions = self.get_revisions(1)
        return revisions[0]['date'] if revisions else None


    ########################################################################
    # Indexing
    ########################################################################
    def to_text(self):
        """This function must return:
           1) An unicode text.
            or
           2) A dict in a multilingual context:
              {'fr': u'....',
               'en': u'....' ....}
        """
        raise NotImplementedError


    def _get_catalog_values(self):
        from access import RoleAware
        from file import File, Image
        from folder import Folder

        # Values
        abspath = self.get_canonical_path()
        # Get the languages
        site_root = self.get_site_root()
        languages = site_root.get_property('website_languages')

        # Titles
        title = {}
        for language in languages:
            title[language] = self.get_title(language=language)

        # Descriptions
        description = {}
        for language in languages:
            description[language] = self.get_property('description',
                                                      language=language)

        # Subjects (keywords)
        subject = {}
        for language in languages:
            subject[language] = self.get_property('subject',
                                                  language=language)

        # Full text
        context = get_context()
        text = None
        try:
            server = context.server
        except AttributeError:
            server = None
        if server is not None and server.index_text:
            try:
                text = self.to_text()
            except NotImplementedError:
                pass
            except:
                # FIXME Use a different logger
                server.log_error(context)
#                log = "%s failed" % self.get_abspath()
#               server.event_log.write(log)
#               server.event_log.flush()

        # Parent path
        if abspath == '/':
            parent_path = None
        else:
            i = abspath.rfind('/') + 1
            parent_path = abspath[:i]

        # Size
        if isinstance(self, File):
            # FIXME We add an arbitrary size so files will always be bigger
            # than folders. This won't work when there is a folder with more
            # than that size.
            size = 2**30 + self.get_size()
        else:
            names = self.get_names()
            size = len(names)

        # Workflow state
        if isinstance(self, WorkflowAware):
            workflow_state = self.get_workflow_state()
        else:
            workflow_state = None

        # Role Aware
        is_role_aware = isinstance(self, RoleAware)
        if is_role_aware:
            members = self.get_members()
        else:
            members = None

        # Ok
        return {
            'name': self.name,
            'abspath': abspath,
            'format': self.metadata.format,
            'title': title,
            'subject': subject,
            'text': text,
            'links': self.get_links(),
            'parent_path': parent_path,
            # This should be defined by subclasses
            'is_folder': isinstance(self, Folder),
            'is_image': isinstance(self, Image),
            'is_role_aware': is_role_aware,
            'members': members,
            'size': size,
            'workflow_state': workflow_state,
        }


    def get_catalog_values(self, values=None):
        revisions = self.get_revisions(1, action=1)
        if values is None:
            values = self._get_catalog_values()

        # Get revisions
        revisions = self.get_revisions(action=2)
        if not revisions:
            return values

        # Ok
        revision = revisions[0]
        context = get_context()
        values['last_author'] = context.get_user_title(revision['username'])
        values['mtime'] = revision['date']
        return values


    ########################################################################
    # API
    ########################################################################
    def get_handlers(self):
        """Return all the handlers attached to this resource, except the
        metadata.
        """
        return [self.handler]


    def rename_handlers(self, new_name):
        """Consider we want to rename this resource to the given 'new_name',
        return the old a new names for all the attached handlers (except the
        metadata).

        This method is required by the "move_resource" method.
        """
        return [(self.name, new_name)]


    def _on_move_resource(self, target):
        """This method is to be called when moving the resource somewhere
        else, before it has been moved.  The 'target' parameter is the
        place it will be moved to.

        Called by 'Folder.move_resource'.  It is used to update the resources
        that link to this one.
        """
        # (1) Update links to other resources
        self.update_relative_links(target)

        # (2) Update resources that link to me
        # Check referencial-integrity
        catalog = get_context().database.catalog
        # The catalog is not available when updating (icms-update.py)
        # FIXME We do not guarantee referencial-integrity when updating
        if catalog is None:
            return

        source = self.get_canonical_path()

        # Get all the resources that have a link to me
        query = PhraseQuery('links', str(source))
        results = catalog.search(query).get_documents()
        for result in results:
            resource = self.get_resource(result.abspath)
            resource.update_links(source, target)


    def update_links(self, source, target):
        """The resource identified by 'source' is going to be moved to
        'target'.  Update our links to it.

        The parameters 'source' and 'target' are absolute 'Path' objects.
        """


    def update_relative_links(self, target):
        """Update the relative links coming out from this resource, so they
        are not broken when this resource moves to 'target'.
        """


    def get_links(self):
        return []


    ########################################################################
    # Upgrade
    ########################################################################
    def get_next_versions(self):
        cls_version = self.class_version
        obj_version = self.metadata.get_property('version').value
        # Set zero version if the resource does not have a version
        if obj_version is None:
            obj_version = '00000000'

        # Get all the version numbers
        versions = []
        for cls in self.__class__.mro():
            for name in cls.__dict__.keys():
                if not name.startswith('update_'):
                    continue
                kk, version = name.split('_', 1)
                if len(version) != 8:
                    continue
                try:
                    int(version)
                except ValueError:
                    continue
                if version > obj_version and version <= cls_version:
                    versions.append(version)

        versions.sort()
        return versions


    def update(self, version):
        # We don't check the version is good
        getattr(self, 'update_%s' % version)()
        metadata = self.metadata
        metadata.set_changed()
        metadata.set_property('version', version)


    ########################################################################
    # Lock/Unlock/Put
    ########################################################################
    def lock(self):
        lock = Lock(username=get_context().user.name)

        self = self.get_real_resource()
        if self.parent is None:
            self.handler.set_handler('.lock', lock)
        else:
            self.parent.handler.set_handler('%s.lock' % self.name, lock)

        return lock.key


    def unlock(self):
        self = self.get_real_resource()
        if self.parent is None:
            self.handler.del_handler('.lock')
        else:
            self.parent.handler.del_handler('%s.lock' % self.name)


    def is_locked(self):
        self = self.get_real_resource()
        if self.parent is None:
            return self.handler.has_handler('.lock')
        return self.parent.handler.has_handler('%s.lock' % self.name)


    def get_lock(self):
        self = self.get_real_resource()
        if self.parent is None:
            return self.handler.get_handler('.lock')
        return self.parent.handler.get_handler('%s.lock' % self.name)


    ########################################################################
    # User interface
    ########################################################################
    def get_title(self, language=None):
        title = self.get_property('title', language=language)
        if title:
            return title
        # Fallback to the resource's name
        return unicode(self.name)


    def get_content_language(self, context, languages=None):
        if languages is None:
            site_root = self.get_site_root()
            languages = site_root.get_property('website_languages')

        # The 'content_language' query parameter has preference
        language = context.get_query_value('content_language')
        if language in languages:
            return language

        # Language negotiation
        return context.accept_language.select_language(languages)


    ########################################################################
    # Cut & Paste Resources
    ########################################################################
    def can_paste(self, source):
        """Is the source resource can be pasted into myself.
        Question is "can I handle this type of resource?"
        """
        raise NotImplementedError


    def can_paste_into(self, target):
        """Can I be pasted into the given target.
        Question is "Is this container compatible with myself?"
        """
        # No restriction by default. Functional modules will want to keep
        # their specific resources for them.
        return True


    # Views
    new_instance = NewInstance()
    login = LoginView()
    logout = LogoutView()
    edit = DBResource_Edit()
    add_image = DBResource_AddImage()
    add_link = DBResource_AddLink()
    last_changes = DBResource_LastChanges()
    changes = DBResource_Changes()
    backlinks = DBResource_Backlinks()



###################################
# Register the new catalog fields #
###################################

register_field(
    'abspath', String(is_key_field=True, is_stored=True, is_indexed=True))
register_field('text', Unicode(is_indexed=True))
register_field('title', Unicode(is_stored=True, is_indexed=True))
register_field('description', Unicode(is_indexed=True))
register_field('subject', Unicode(is_indexed=True))
register_field('is_role_aware', Boolean(is_indexed=True))
register_field('is_folder', Boolean(is_indexed=True))
register_field('is_image', Boolean(is_indexed=True))
register_field('format', String(is_stored=True, is_indexed=True))
register_field('workflow_state', String(is_stored=True, is_indexed=True))
register_field('members', String(is_indexed=True, multiple=True))
# Versioning
register_field('mtime', DateTime(is_stored=True, is_indexed=True))
register_field('last_author', String(is_stored=True, is_indexed=False))
# For referencial-integrity, keep links between resources, where a link is the
# physical path.
register_field('links', String(is_indexed=True, multiple=True))
# Folder's view
register_field('parent_path', String(is_indexed=True))
register_field('name', String(is_stored=True, is_indexed=True))
register_field('size', Integer(is_stored=True, is_indexed=False))
# Optimize 'Server.find_site_root'
register_field('vhosts', String(is_indexed=True, multiple=True))
# Calendaring
register_field('dtstart', DateTime(is_indexed=True, is_stored=True))
register_field('dtend', DateTime(is_indexed=True, is_stored=True))

