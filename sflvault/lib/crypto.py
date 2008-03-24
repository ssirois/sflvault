"""Provides function to serialize and unserialize cryptographic blobs"""

from Crypto.Util.number import long_to_bytes, bytes_to_long
from base64 import b64decode, b64encode

#
# Deal with ElGamal pubkey and messages serialization.
#
# TODO: DRY those 6 functions, they are found in sflvault.py
def serial_elgamal_msg(stuff):
    """Get a 2-elements tuple of str(), return a string."""
    ns = b64encode(stuff[0]) + ':' + \
         b64encode(stuff[1])
    return ns

def unserial_elgamal_msg(stuff):
    """Get a string, return a 2-elements tuple of str()"""
    x = stuff.split(':')
    return (b64decode(x[0]),
            b64decode(x[1]))

def serial_elgamal_pubkey(stuff):
    """Get a 3-elements tuple of long(), return a string."""
    ns = b64encode(long_to_bytes(stuff[0])) + ':' + \
         b64encode(long_to_bytes(stuff[1])) + ':' + \
         b64encode(long_to_bytes(stuff[2]))         
    return ns

def unserial_elgamal_pubkey(stuff):
    """Get a string, return a 3-elements tuple of long()"""
    x = stuff.split(':')
    return (bytes_to_long(b64decode(x[0])),
            bytes_to_long(b64decode(x[1])),
            bytes_to_long(b64decode(x[2])))

def serial_elgamal_privkey(stuff):
    """Get a 2-elements tuple of long(), return a string."""
    ns = b64encode(long_to_bytes(stuff[0])) + ':' + \
         b64encode(long_to_bytes(stuff[1]))
    return ns

def unserial_elgamal_privkey(stuff):
    """Get a string, return a 2-elements tuple of long()"""
    x = stuff.split(':')
    return (bytes_to_long(b64decode(x[0])),
            bytes_to_long(b64decode(x[1])))


#
# Encryption / decryption stuff
#

