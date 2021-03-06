
"""
oauthlib.oauth2.draft25.tokens
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains methods for adding two types of access tokens to requests.

- Bearer http://tools.ietf.org/html/draft-ietf-oauth-saml2-bearer-08
- MAC http://tools.ietf.org/html/draft-ietf-oauth-v2-http-mac-00

"""
import hashlib
import hmac
from binascii import b2a_base64
from urllib.parse import urlparse

from . import utils


def prepare_mac_header(token, uri, key, http_method, nonce=None, headers=None,
                       body=None, ext='', hash_algorithm='hmac-sha-1'):
    """Add an `MAC Access Authentication`_ signature to headers.

    Unlike OAuth 1, this HMAC signature does not require inclusion of the request
    payload/body, neither does it use a combination of client_secret and
    token_secret but rather a mac_key provided together with the access token.

    Currently two algorithms are supported, "hmac-sha-1" and "hmac-sha-256",
    `extension algorithms`_ are not supported.

    Example MAC Authorization header, linebreaks added for clarity

    Authorization: MAC id="h480djs93hd8",
                       nonce="1336363200:dj83hs9s",
                       mac="bhCQXTVyfj5cmA9uKkPFx1zeOXM="

    .. _`MAC Access Authentication`: http://tools.ietf.org/html/draft-ietf-oauth-v2-http-mac-01
    .. _`extension algorithms`: http://tools.ietf.org/html/draft-ietf-oauth-v2-http-mac-01#section-7.1

    :param uri: Request URI.
    :param headers: Request headers as a dictionary.
    :param http_method: HTTP Request method.
    :param key: MAC given provided by token endpoint.
    :param algorithm: HMAC algorithm provided by token endpoint.
    :return: headers dictionary with the authorization field added.
    """
    http_method = http_method.upper()
    host, port = utils.host_from_uri(uri)

    if hash_algorithm.lower() == 'hmac-sha-1':
        h = hashlib.sha1
    else:
        h = hashlib.sha256

    nonce = nonce or '{0}:{1}'.format(utils.generate_nonce(), utils.generate_timestamp())
    sch, net, path, par, query, fra = urlparse(uri)

    if query:
        request_uri = path + '?' + query
    else:
        request_uri = path

    # Hash the body/payload
    if body is not None:
        bodyhash = b2a_base64(h(body).digest())[:-1].decode('utf-8')
    else:
        bodyhash = ''

    # Create the normalized base string
    base = []
    base.append(nonce)
    base.append(http_method.upper())
    base.append(request_uri)
    base.append(host)
    base.append(port)
    base.append(bodyhash)
    base.append(ext)
    base_string = '\n'.join(base) + '\n'

    # hmac struggles with unicode strings - http://bugs.python.org/issue5285
    if isinstance(key, str):
        key = key.encode('utf-8')
    sign = hmac.new(key, base_string, h)
    sign = b2a_base64(sign.digest())[:-1].decode('utf-8')

    header = []
    header.append('MAC id="%s"' % token)
    header.append('nonce="%s"' % nonce)
    if bodyhash:
        header.append('bodyhash="%s"' % bodyhash)
    if ext:
        header.append('ext="%s"' % ext)
    header.append('mac="%s"' % sign)

    headers = headers or {}
    headers['Authorization'] = ', '.join(header)
    return headers


def prepare_bearer_uri(token, uri):
    """Add a `Bearer Token`_ to the request URI.
    Not recommended, use only if client can't use authorization header or body.

    http://www.example.com/path?access_token=h480djs93hd8

    .. _`Bearer Token`: http://tools.ietf.org/html/draft-ietf-oauth-v2-bearer-18
    """
    return utils.add_params_to_uri(uri, [(('access_token', token))])


def prepare_bearer_headers(token, headers=None):
    """Add a `Bearer Token`_ to the request URI.
    Recommended method of passing bearer tokens.

    Authorization: Bearer h480djs93hd8

    .. _`Bearer Token`: http://tools.ietf.org/html/draft-ietf-oauth-v2-bearer-18
    """
    headers = headers or {}
    headers['Authorization'] = 'Bearer %s' % token
    return headers


def prepare_bearer_body(token, body=''):
    """Add a `Bearer Token`_ to the request body.

    access_token=h480djs93hd8

    .. _`Bearer Token`: http://tools.ietf.org/html/draft-ietf-oauth-v2-bearer-18
    """
    return utils.add_params_to_qs(body, [(('access_token', token))])
