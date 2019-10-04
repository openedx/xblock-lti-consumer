"""
Utility functions for working with OAuth signatures.
"""

from __future__ import absolute_import, unicode_literals

import base64
import hashlib
import logging

import six.moves.urllib.error
import six.moves.urllib.parse
import six
from oauthlib import oauth1

from .exceptions import LtiError

log = logging.getLogger(__name__)


class SignedRequest(object):  # pylint: disable=bad-option-value, useless-object-inheritance
    """
    Encapsulates request attributes needed when working
    with the `oauthlib.oauth1` API
    """
    def __init__(self, **kwargs):
        self.uri = kwargs.get('uri')
        self.http_method = kwargs.get('http_method')
        self.params = kwargs.get('params')
        self.oauth_params = kwargs.get('oauth_params')
        self.headers = kwargs.get('headers')
        self.body = kwargs.get('body')
        self.decoded_body = kwargs.get('decoded_body')
        self.signature = kwargs.get('signature')


def get_oauth_request_signature(key, secret, url, headers, body):
    """
    Returns Authorization header for a signed oauth request.

    Arguments:
        key (str): LTI provider key
        secret (str): LTI provider secret
        url (str): URL for the signed request
        header (str): HTTP headers for the signed request
        body (str): Body of the signed request

    Returns:
        str: Authorization header for the OAuth signed request
    """
    client = oauth1.Client(client_key=six.text_type(key), client_secret=six.text_type(secret))
    try:
        # Add Authorization header which looks like:
        # Authorization: OAuth oauth_nonce="80966668944732164491378916897",
        # oauth_timestamp="1378916897", oauth_version="1.0", oauth_signature_method="HMAC-SHA1",
        # oauth_consumer_key="", oauth_signature="frVp4JuvT1mVXlxktiAUjQ7%2F1cw%3D"
        _, headers, _ = client.sign(
            six.text_type(url.strip()),
            http_method=u'POST',
            body=body,
            headers=headers
        )
    except ValueError:  # Scheme not in url.
        raise LtiError("Failed to sign oauth request")

    return headers['Authorization']


def verify_oauth_body_signature(request, lti_provider_secret, service_url):
    """
    Verify grade request from LTI provider using OAuth body signing.

    Uses http://oauth.googlecode.com/svn/spec/ext/body_hash/1.0/oauth-bodyhash.html::

        This specification extends the OAuth signature to include integrity checks on HTTP request bodies
        with content types other than application/x-www-form-urlencoded.

    Arguments:
        request (xblock.django.request.DjangoWebobRequest): Request object for current HTTP request
        lti_provider_secret (str): Secret key for the LTI provider
        service_url (str): URL that the request was made to
        content_type (str): HTTP content type of the request

    Raises:
        LtiError if request is incorrect.
    """

    headers = {
        'Authorization': six.text_type(request.headers.get('Authorization')),
        'Content-Type': request.content_type,
    }

    sha1 = hashlib.sha1()
    sha1.update(request.body)
    oauth_body_hash = base64.b64encode(sha1.digest())  # pylint: disable=E1121
    oauth_params = oauth1.rfc5849.signature.collect_parameters(headers=headers, exclude_oauth_signature=False)
    oauth_headers = dict(oauth_params)
    oauth_signature = oauth_headers.pop('oauth_signature')
    mock_request_lti_1 = SignedRequest(
        uri=six.text_type(six.moves.urllib.parse.unquote(service_url)),
        http_method=six.text_type(request.method),
        params=list(oauth_headers.items()),
        signature=oauth_signature
    )
    mock_request_lti_2 = SignedRequest(
        uri=six.text_type(six.moves.urllib.parse.unquote(request.url)),
        http_method=six.text_type(request.method),
        params=list(oauth_headers.items()),
        signature=oauth_signature
    )
    if oauth_body_hash.decode('utf-8') != oauth_headers.get('oauth_body_hash'):
        log.error(
            "OAuth body hash verification failed, provided: %s, "
            "calculated: %s, for url: %s, body is: %s",
            oauth_headers.get('oauth_body_hash'),
            oauth_body_hash,
            service_url,
            request.body
        )
        raise LtiError("OAuth body hash verification is failed.")

    if (not oauth1.rfc5849.signature.verify_hmac_sha1(mock_request_lti_1, lti_provider_secret) and not
            oauth1.rfc5849.signature.verify_hmac_sha1(mock_request_lti_2, lti_provider_secret)):
        log.error(
            "OAuth signature verification failed, for "
            "headers:%s url:%s method:%s",
            oauth_headers,
            service_url,
            six.text_type(request.method)
        )
        raise LtiError("OAuth signature verification has failed.")

    return True


def log_authorization_header(request, client_key, client_secret):
    """
    Helper function that logs proper HTTP Authorization header for a given request

    Used only in debug situations, this logs the correct Authorization header based on
    the request header and body according to OAuth 1 Body signing

    Arguments:
        request (xblock.django.request.DjangoWebobRequest):  Request object to log Authorization header for

    Returns:
        nothing
    """
    sha1 = hashlib.sha1()
    sha1.update(request.body)
    oauth_body_hash = six.text_type(base64.b64encode(sha1.digest()))  # pylint: disable=too-many-function-args
    log.debug("[LTI] oauth_body_hash = %s", oauth_body_hash)
    client = oauth1.Client(client_key, client_secret)
    params = client.get_oauth_params(request)
    params.append((u'oauth_body_hash', oauth_body_hash))
    mock_request = SignedRequest(
        uri=six.text_type(six.moves.urllib.parse.unquote(request.url)),
        headers=request.headers,
        body=u"",
        decoded_body=u"",
        oauth_params=params,
        http_method=six.text_type(request.method),
    )
    sig = client.get_oauth_signature(mock_request)
    mock_request.oauth_params.append((u'oauth_signature', sig))

    __, headers, _ = client._render(mock_request)  # pylint: disable=protected-access
    log.debug(
        "\n\n#### COPY AND PASTE AUTHORIZATION HEADER ####\n%s\n####################################\n\n",
        headers['Authorization']
    )
