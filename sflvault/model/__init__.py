# -=- encoding: utf-8 -=-
#
# SFLvault - Secure networked password store and credentials manager.
#
# Copyright (C) 2008  Savoir-faire Linux inc.
#
# Author: Alexandre Bourget <alexandre.bourget@savoirfairelinux.com>
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

from pylons import config
from sqlalchemy import Column, MetaData, Table, types, ForeignKey
from sqlalchemy.orm import mapper, relation, backref
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import *

from Crypto.PublicKey import ElGamal
from base64 import b64decode, b64encode

from sflvault.lib.crypto import *

# Global session manager.  Session() returns the session object
# appropriate for the current web request.
Session = scoped_session(sessionmaker(autoflush=True, transactional=True,
                                      bind=config['pylons.g'].sa_engine))

mapper = Session.mapper


# Global metadata. If you have multiple databases with overlapping table
# names, you'll need a metadata for each database.
metadata = MetaData()


users_table = Table("users", metadata,
                    Column('id', types.Integer, primary_key=True),
                    Column('username', types.Unicode(50)),
                    # ElGamal public key.
                    Column('pubkey', types.Text),
                    # Used in the login/authenticate challenge
                    Column('logging_token', types.Binary(35)),
                    # Time until the token is valid.
                    Column('logging_timeout', types.DateTime),
                    # This stamp is used to wipe users which haven't 'setup'
                    # their account before this date/time
                    Column('waiting_setup', types.DateTime, nullable=True),
                    Column('created_time', types.DateTime, default=datetime.now()),
                    # Admin flag, allows to add users, and grant access.
                    Column('is_admin', types.Boolean, default=False)
                    )

userlevels_table = Table('userlevels', metadata,
                         Column('id', types.Integer, primary_key=True),
                         Column('user_id', types.Integer, ForeignKey('users.id')),
                         Column('level', types.Unicode(50), index=True)
                         )

customers_table = Table('customers', metadata,
                        Column('id', types.Integer, primary_key=True),
                        Column('name', types.Unicode(100)),
                        Column('created_time', types.DateTime),
                        # username, même si yé effacé.
                        Column('created_user', types.Unicode(50))
                        )

servers_table = Table('servers', metadata,
                      Column('id', types.Integer, primary_key=True),
                      Column('customer_id', types.Integer, ForeignKey('customers.id')), # relation customers
                      Column('created_time', types.DateTime),
                      # Unicode lisible, un peu de descriptif
                      Column('name', types.Unicode(150)),
                      # Domaine complet.
                      Column('fqdn', types.Unicode(150)),
                      # Adresse IP si fixe, sinon 'dyn'
                      Column('ip', types.String(100)),
                      # Où il est ce serveur, location géographique, et dans
                      # la ville et dans son boîtier (4ième ?)
                      Column('location', types.Text),
                      # Notes sur le serveur, références, URLs, etc..
                      Column('notes', types.Text)
                      )

# Each ssh or web app. service that have a password.
services_table = Table('services', metadata,
                       Column('id', types.Integer, primary_key=True),
                       Column('server_id', types.Integer, ForeignKey('servers.id')), # relation servers
                       # Type of service, eventually, linked to specific plug-ins.
                       # TODO: ajouter le parent_service_id..
                       Column('parent_service_id', types.Integer, ForeignKey('services.id')),
                       Column('url', types.String(250)),
                       Column('hostname', types.String(250)),
                       Column('port', types.Integer),
                       Column('loginname', types.String(50)),
                       Column('type', types.String(50)),
                       Column('level', types.Unicode(50)),
                       Column('secret', types.Text),
                       # simplejson'd python structures, depends on 'type'
                       Column('metadata', types.Text), # reserved.
                       # Add some created_time, modified_time, etc...
                       Column('notes', types.Text),
                       Column('secret_last_modified', types.DateTime)
                       )

# Table of encrypted symkeys for each 'secret' in the services_table, one for each user.
userciphers_table = Table('userciphers', metadata,
                          Column('id', types.Integer, primary_key=True),
                          Column('service_id', types.Integer, ForeignKey('services.id')), # relation to services
                          # The user for which this secret is encrypted
                          Column('user_id', types.Integer, ForeignKey('users.id')),
                          # Encrypted symkey with user's pubkey.
                          Column('stuff', types.Text)
                          )

class Service(object):
    def __repr__(self):
        return "<Service s#%d: %s>" % (self.id, self.url)

class Server(object):
    def __repr__(self):
        return "<Server m#%d: %s (%s %s)>" % (self.id, self.name, self.fqdn, self.ip)

class Usercipher(object):
    def __repr__(self):
        return "<Usercipher: %s - service_id: %d>" % (self.user, self.service_id)

class User(object):
    def setup_expired(self):
        """Return True/False if waiting_setup has expired"""
        if (not self.waiting_setup):
            return True
        elif (datetime.now() < self.waiting_setup):
            return False
        else:
            return True

    def elgamal(self):
        """Return the ElGamal object, ready to encrypt stuff."""
        e = ElGamal.ElGamalobj()
        (e.p, e.g, e.y) = unserial_elgamal_pubkey(self.pubkey)
        return e
    
    def __repr__(self):
        return "<User u#%d: %s>" % (self.id, self.username)

class UserLevel(object):
    def __repr__(self):
        return "<UserLevel: %s>" % (self.level)

class Customer(object):
    def __repr__(self):
        return "<Customer c#%d: %s>" % (self.id, self.name)

# Map each class to its corresponding table.
mapper(User, users_table, {
    'levels': relation(UserLevel, backref='user', lazy=False),
    'ciphers': relation(Usercipher, backref='user', lazy=False)
    })
mapper(UserLevel, userlevels_table, {
    
    })
mapper(Customer, customers_table, {
    'servers': relation(Server, backref='customer', lazy=False)
    })
mapper(Server, servers_table, {
    'services': relation(Service, backref='server', lazy=False)
    })
mapper(Service, services_table, {
    'children': relation(Service,
                         lazy=False,
                         backref=backref('parent', uselist=False, remote_side=[services_table.c.id]),
                         primaryjoin=services_table.c.parent_service_id==services_table.c.id),
    
    })
mapper(Usercipher, userciphers_table, {
    
    })
