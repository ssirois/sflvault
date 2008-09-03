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

from sflvault.client.remoting import *
from sflvault.client.utils import *
import struct, fcntl, termios, signal # for term size signaling..
import pexpect
import pxssh
import sys


# Enum used in the services' `provides`
PROV_PORT_FORWARD  = 'port-forward'
PROV_SHELL_ACCESS  = 'shell-access'
PROV_MYSQL_CONSOLE = 'mysql-console'

# Operational modes
OP_DIRECT = 'direct-access'            # - When, let's say 'ssh' is going to spawn a
                                       # process.
OP_THRGH_FWD_PORT = 'through-fwd-port' # - When we must go through a port that's been
                                       # forwarded.
                                       # In that case, the parent must provide with
                                       # forwarded host and port.
OP_THRGH_SHELL = 'through-shell'       # - When a command must be sent through an open
                                       # shell



# Helper func

def print_cnx(cnx):
    sys.stdout.write(cnx.before)
    sys.stdout.write(cnx.after)
    sys.stdout.flush()



### Service definitions

class ExpectClass(object):
    def __init__(self, service_obj):
        # Hold the parent Service object here..
        self.service = service_obj
        self.error = None

        # Quick references..
        self.cnx = service_obj.shell_handle
        timeout = service_obj.timeout

        funcs = []
        strings = []
        for x in dir(self):
            if x.startswith('_'):
                continue
            
            func = getattr(self, x)

            if callable(func) and func.__doc__:
                funcs.append(func)
                strings.append(func.__doc__)


        try:
            idx = self.cnx.expect(strings, timeout=timeout)
        except pexpect.TIMEOUT, e:
            self._flush()
            if hasattr(self, '_timeout'):
                self._timeout()
            else:
                sys.stdout.write("\nTimed out")

            self.error = "Timed out"
            raise ServiceExpectError("Timed out")

        self._flush()

        funcs[idx]()
    
    
    def _flush(self):
        sys.stdout.write(self.cnx.before)
        sys.stdout.write(self.cnx.after)
        sys.stdout.flush()


class ShellService(Service):
    """Abstract class for services running over ssh. Helper funcs."""


    def __init__(self, data, timeout=45):
        # Call parent
        Service.__init__(self, data, timeout)
        
    def interact(self):

        # To grab the window changing signals
        def sigwinch_passthrough (sig, data):
            s = struct.pack("HHHH", 0, 0, 0, 0)
            a = struct.unpack('hhhh', fcntl.ioctl(sys.stdout.fileno(),
                                                  termios.TIOCGWINSZ , s))
            self.shell_handle.setwinsize(a[0],a[1])

        # Map window resizing signal to function
        signal.signal(signal.SIGWINCH, sigwinch_passthrough)

        # Call USER's terminal and get term size.
        s = struct.pack("HHHH", 0, 0, 0, 0)
        fd_stdout = sys.stdout.fileno()
        x = fcntl.ioctl(fd_stdout, termios.TIOCGWINSZ, s)
        sz = struct.unpack("HHHH", x)
        # Send to the remote terminals..
        self.shell_handle.setwinsize(sz[0], sz[1])


        try:
            # Go ahead, you're free to go !
            self.shell_handle.interact()

            # Reset signal
            signal.signal(signal.SIGWINCH, signal.SIG_DFL)

            print "[SFLvault] Escaped from %s, calling postwork." % self.__class__.__name__
        except OSError, e:
            print "[SFLvault] %s disconnected" % self.__class__.__name__


    def postwork(self):
        
        # If we're the last, let's just close the connection.
        if not self.parent:
            self.shell_handle.close()




class ssh(ShellService):
    """ssh protocol service handler"""

    # Modes this service handler can provide
    provides_modes = [PROV_SHELL_ACCESS, PROV_PORT_FORWARD]
    

    def required(self, provide=None):
        """Verify if this service handler can provide `provide` type of connection.

        Child can ask for SHELL_ACCESS or PORT_FORWARD to be provided. It can also
        ask for nothing. It is the case of the last child, which has required()
        invoked with mode=None, since there's no other child that requires something.

        When mode=None, plugin is most probably the last child, and the end to
        which we want to connect."""

        if not self.child and not self.parent:
            # We're alone in the world, we've setting up DIRECT access (spawn a
            # process)
            self.operation_mode = OP_DIRECT
            self.provide_mode = PROV_SHELL_ACCESS
            return True

        # We can provide SHELL or FORWARD, so it's as you wish Mr. required() !
        if self.provides(provide):
            self.provide_mode = provide
        else:
            # Sorry, we don't know what you're talking about :)
            raise ServiceRequireError("ssh module can't provide '%s'" % provide)
            
        if not self.parent:
            # If there's no parent, then we're going to spawn ourself.
            self.operation_mode = OP_DIRECT

            return True
        else:
            # Otherwise, 'ssh' must be called from within a shell.
            self.operation_mode = OP_THRGH_SHELL
            return self.parent.required(PROV_SHELL_ACCESS)


    def prework(self):

        # Default user:
        user = self.url.username or 'root'

        sshcmd = "ssh -l %s %s" % (user, self.url.hostname)

        if self.url.port:
            sshcmd += " -p %d" % (self.url.port)

        if self.operation_mode == OP_DIRECT:
            print "Trying to login to %s as %s ..." % (self.url.hostname, user)
            cnx = pexpect.spawn(sshcmd)
        elif self.operation_mode == OP_THRGH_SHELL:
            cnx = self.parent.shell_handle
            cnx.sendline(sshcmd)
        else:
            # NOTE: This should be dead code:
            raise RemotingError("No way to go through there. Woah? How did we get here ?")

        self.shell_handle = cnx

        idx = cnx.expect(['assword:', 'Last login',
                         "(?i)are you sure you want to continue connecting"],
                         timeout=self.timeout)

        print_cnx(cnx)
        
        if idx == 2:
            cnx.sendline('yes')
            idx = cnx.expect(['assword:', 'Last login'],
                             timeout=self.timeout)
            print_cnx(cnx)
        
        if idx == 0:
            # Send password
            sys.stdout.write(" [sending password...] ")
            cnx.sendline(self.data['plaintext'])
            idx = cnx.expect([r'[^ ]*@.*:.*[$#]'], timeout=self.timeout)
            if idx == 0:
                print_cnx(cnx)
        else:
            # We're in!
            print "We're in! (using shared-key?)"



# TODO: document that the `sudo` doesn't need a password, it takes the password
# from the parent service.
class sudo(ShellService):
    """sudo app. service handler"""

    provides_modes = [PROV_SHELL_ACCESS]

    def required(self, provide=None):
        """Check requirements for sudo"""

        # We must be over an 'ssh' to do anything!
        if not self.parent or not self.parent.required(PROV_SHELL_ACCESS):
            raise ServiceRequireError("Sudo must be child of a shell")

        # We can provide SHELL
        if not self.provides(provide):
            
            raise ServiceRequireError("sudo module can't provide '%s'" % provide)

        # TODO: pass-through PORT_FORWARD provisioning if child supports it..
        return True


    def prework(self):
        # Inherit shell handle
        self.shell_handle = self.parent.shell_handle

        class expect_waitshell(ExpectClass):
            def gotshell(self):
                r'[^ ]*@.*:.*[$#]'
                
                return True

            def failed(self):
                'assword:'
                raise ServiceExpectError("Failed to authenticate sudo://")

            def failed2(self):
                'Sorry'
                self.failed()

        class expect_sudowork(ExpectClass):
            def sendpass(self):
                'assword:'

                sys.stdout.write(" [sending password...] ")
                self.cnx.sendline(self.service.parent.data['plaintext'])

                expect_waitshell(self.service)

        # Send command
        self.shell_handle.sendline('sudo -s')

        expect_sudowork(self)
        
        

    # Call parent
    #def interact(self):

    # Call parent
    #def postwork(self):

    
class su(ShellService):
    """su app. service handler"""

    # Modes this service handler provides
    provides_modes = [PROV_SHELL_ACCESS]



# Inheritance from 'ssh'
class mysql(ShellService):
    """mysql app. service handler"""

    provides_modes = [PROV_MYSQL_CONSOLE]

    def __init__(self, data, timeout=45):

        # Call parent
        ssh.__init__(self, data, timeout)
        
    def required(self, provide=None):
        """Verify if this service handler can provide `provide` type of connection.

        Child can ask for SHELL_ACCESS or PORT_FORWARD to be provided. It can also
        ask for nothing. It is the case of the last child, which has required()
        invoked with mode=None, since there's no other child that requires something.

        When mode=None, plugin is most probably the last child, and the end to
        which we want to connect."""

        if self.provides(provide):
            self.provide_mode = provide
        else:
            # Sorry, we don't know what you're talking about :)
            raise ServiceRequireError("mysql module can't provide '%s'" % provide)
        
        if not self.parent:
            raise ServiceRequireError("mysql service can't be executed locally, it has to be behind a SHELL_ACCESS-providing module.")

        self.operation_mode = OP_THRGH_SHELL
        return self.parent.required(PROV_SHELL_ACCESS)


    def prework(self):

        # Bring over here the parent's shell handle.
        cnx = self.parent.shell_handle
        self.shell_handle = cnx

        # Select a database directly ?
        db = ''
        if self.url.path:
            if self.url.path != '/':
                db = self.url.path.lstrip('/')
                
        cmd = "mysql -u %s -p %s" % (self.url.username, db)

        cnx.sendline(cmd)

        idx = cnx.expect(['assword:', 'ERROR \d*'], timeout=self.timeout)
        sys.stdout.write(cnx.before)
        sys.stdout.write(cnx.after)
        
        if idx == 0:
            sys.stdout.write(" [sending password...] ")
            cnx.sendline(self.data['plaintext'])
            idx = cnx.expect(['mysql>', 'ERROR \d*'], timeout=self.timeout)
            if idx == 0:
                sys.stdout.write(cnx.before)
                sys.stdout.write(cnx.after)
            else:
                raise RemotingError("Failed to authenticate with mysql")
        else:
            raise RemotingError("Failed authentication for mysql at program launch")


    # interact() and postwork() inherited

class vnc(Service):
    """vnc protocol service handler"""

    # Modes this service handler provides
    provides_modes = []

