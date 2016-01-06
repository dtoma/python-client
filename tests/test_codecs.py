# coding: utf-8
from coreapi.codecs import CoreJSONCodec, HTMLCodec
from coreapi.codecs import negotiate_decoder, negotiate_encoder
from coreapi.codecs.corejson import _document_to_primative, _primative_to_document
from coreapi.document import Document, Link, Error, required
from coreapi.exceptions import ParseError, NotAcceptable
import pytest


@pytest.fixture
def json_codec():
    return CoreJSONCodec()


@pytest.fixture
def html_codec():
    return HTMLCodec()


@pytest.fixture
def doc():
    return Document(
        url='http://example.org/',
        title='Example',
        content={
            'integer': 123,
            'dict': {'key': 'value'},
            'list': [1, 2, 3],
            'link': Link(url='http://example.org/'),
            'nested': {'child': Link(url='http://example.org/123')},
            '_type': 'needs escaping'
        })


# Documents have a mapping to python primatives in JSON style.

def test_document_to_primative(doc):
    data = _document_to_primative(doc)
    assert data == {
        '_type': 'document',
        '_meta': {
            'url': 'http://example.org/',
            'title': 'Example'
        },
        'integer': 123,
        'dict': {'key': 'value'},
        'list': [1, 2, 3],
        'link': {'_type': 'link'},
        'nested': {'child': {'_type': 'link', 'url': '/123'}},
        '__type': 'needs escaping'
    }


def test_primative_to_document(doc):
    data = {
        '_type': 'document',
        '_meta': {
            'url': 'http://example.org/',
            'title': 'Example'
        },
        'integer': 123,
        'dict': {'key': 'value'},
        'list': [1, 2, 3],
        'link': {'_type': 'link', 'url': 'http://example.org/'},
        'nested': {'child': {'_type': 'link', 'url': 'http://example.org/123'}},
        '__type': 'needs escaping'
    }
    assert _primative_to_document(data) == doc


def test_error_to_primative():
    error = Error(['failed'])
    data = {
        '_type': 'error',
        'messages': ['failed']
    }
    assert _document_to_primative(error) == data


def test_primative_to_error():
    error = Error(['failed'])
    data = {
        '_type': 'error',
        'messages': ['failed']
    }
    assert _primative_to_document(data) == error


# Codecs can load a document successfully.

def test_minimal_document(json_codec):
    """
    Ensure we can load the smallest possible valid JSON encoding.
    """
    doc = json_codec.load(b'{"_type":"document"}')
    assert isinstance(doc, Document)
    assert doc.url == ''
    assert doc.title == ''
    assert doc == {}


def test_minimal_error(json_codec):
    """
    Ensure we can load a minimal error message encoding.
    """
    error = json_codec.load(b'{"_type":"error","messages":["failed"]}')
    assert isinstance(error, Error)
    assert error == ['failed']


# Parse errors should be raised for invalid encodings.

def test_malformed_json(json_codec):
    """
    Invalid JSON should raise a ParseError.
    """
    with pytest.raises(ParseError):
        json_codec.load(b'_')


def test_not_a_document(json_codec):
    """
    Valid JSON that does not return a document as the top level element
    should raise a ParseError.
    """
    with pytest.raises(ParseError):
        json_codec.load(b'{}')


# Encodings may have a verbose and a compact style.

def test_compact_style(json_codec):
    doc = Document(content={'a': 123, 'b': 456})
    bytes = json_codec.dump(doc)
    assert bytes == b'{"_type":"document","a":123,"b":456}'


def test_verbose_style(json_codec):
    doc = Document(content={'a': 123, 'b': 456})
    bytes = json_codec.dump(doc, indent=True)
    assert bytes == b"""{
    "_type": "document",
    "a": 123,
    "b": 456
}"""


# Links should use compact format for optional fields, verbose for required.

def test_link_encodings(json_codec):
    doc = Document(content={
        'link': Link(
            action='post',
            transition='inline',
            fields=['optional', required('required')]
        )
    })
    bytes = json_codec.dump(doc, indent=True)
    assert bytes == b"""{
    "_type": "document",
    "link": {
        "_type": "link",
        "action": "post",
        "transition": "inline",
        "fields": [
            "optional",
            {
                "name": "required",
                "required": true
            }
        ]
    }
}"""


# Tests for graceful omissions.

def test_invalid_document_meta_ignored(json_codec):
    doc = json_codec.load(b'{"_type": "document", "_meta": 1, "a": 1}')
    assert doc == Document(content={"a": 1})


def test_invalid_document_url_ignored(json_codec):
    doc = json_codec.load(b'{"_type": "document", "_meta": {"url": 1}, "a": 1}')
    assert doc == Document(content={"a": 1})


def test_invalid_document_title_ignored(json_codec):
    doc = json_codec.load(b'{"_type": "document", "_meta": {"title": 1}, "a": 1}')
    assert doc == Document(content={"a": 1})


def test_invalid_link_url_ignored(json_codec):
    doc = json_codec.load(b'{"_type": "document", "link": {"_type": "link", "url": 1}}')
    assert doc == Document(content={"link": Link()})


def test_invalid_link_fields_ignored(json_codec):
    doc = json_codec.load(b'{"_type": "document", "link": {"_type": "link", "fields": 1}}')
    assert doc == Document(content={"link": Link()})


def test_invalid_message_field_ignored(json_codec):
    error = json_codec.load(b'{"_type": "error", "messages": 1}')
    assert error == Error(messages=[])


# Tests for 'Content-Type' header lookup.

def test_get_default_decoder():
    assert isinstance(negotiate_decoder(), CoreJSONCodec)


def test_get_supported_decoder():
    assert isinstance(negotiate_decoder('application/vnd.coreapi+json'), CoreJSONCodec)


def test_get_supported_decoder_with_parameters():
    assert isinstance(negotiate_decoder('application/vnd.coreapi+json; verison=1.0'), CoreJSONCodec)


def test_get_unsupported_decoder():
    with pytest.raises(ParseError):
        negotiate_decoder('application/csv')


def test_get_render_only_decoder():
    with pytest.raises(ParseError):
        negotiate_decoder('text/html')


# Tests for 'Accept' header lookup.

def test_get_default_encoder():
    content_type, codec = negotiate_encoder()
    assert content_type == 'application/vnd.coreapi+json'
    assert isinstance(codec, CoreJSONCodec)


def test_encoder_preference():
    content_type, codec = negotiate_encoder(
        accept='text/html; q=1.0, application/vnd.coreapi+json; q=1.0'
    )
    assert content_type == 'application/vnd.coreapi+json'
    assert isinstance(codec, CoreJSONCodec)


def test_get_accepted_encoder():
    content_type, codec = negotiate_encoder(accept='application/vnd.coreapi+json')
    assert content_type == 'application/vnd.coreapi+json'
    assert isinstance(codec, CoreJSONCodec)


def test_get_underspecified_encoder():
    content_type, codec = negotiate_encoder(accept='text/*')
    assert content_type == 'text/html'
    assert isinstance(codec, HTMLCodec)


def test_get_unsupported_encoder():
    with pytest.raises(NotAcceptable):
        negotiate_encoder('application/csv')


def test_get_unsupported_encoder_with_fallback():
    content_type, codec = negotiate_encoder(accept='application/csv, */*')
    assert content_type == 'application/vnd.coreapi+json'
    assert isinstance(codec, CoreJSONCodec)


# Tests for HTML rendering

def test_html_document_rendering(html_codec):
    doc = Document({'string': 'abc', 'int': 123, 'bool': True})
    content = html_codec.dump(doc)
    assert 'coreapi-document' in content
    assert '<span>abc</span>' in content
    assert '<code>123</code>' in content
    assert '<code>true</code>' in content


def test_html_object_rendering(html_codec):
    doc = Document({'object': {'a': 1, 'b': 2}})
    content = html_codec.dump(doc)
    assert 'coreapi-object' in content
    assert '<th>a</th>' in content
    assert '<th>b</th>' in content


def test_html_array_rendering(html_codec):
    doc = Document({'array': [1, 2]})
    content = html_codec.dump(doc)
    assert 'coreapi-array' in content
    assert '<th>0</th>' in content
    assert '<th>1</th>' in content


def test_html_link_rendering(html_codec):
    doc = Document({'link': Link(url='/test/')})
    content = html_codec.dump(doc)
    assert 'coreapi-link' in content
    assert 'href="/test/"' in content


def test_html_error_rendering(html_codec):
    doc = Error(['something failed'])
    content = html_codec.dump(doc)
    assert 'coreapi-error' in content
    assert 'something failed' in content
