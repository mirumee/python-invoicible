# -coding: utf-8 -
import datetime
import decimal
import httplib
import oauth.oauth as oauth
import pprint
import simplejson
import urllib
import urlparse

DELETED = 204
BAD_REQUEST = 400
FORBIDDEN = 401
NOT_FOUND = 404
DUPLICATE_ENTRY = 409
NOT_HERE = 410
INTERNAL_ERROR = 500
NOT_IMPLEMENTED = 501
THROTTLED = 503

DEBUG=True

DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
DATE_FORMAT = '%Y-%m-%d'

class DoesNotExists(Exception):
    pass

class ValidationError(Exception):
    pass

class Client(oauth.OAuthClient):
    def __init__(self, consumer_key, consumer_secret,
                access_token_key, access_token_secret,
                invoicible_domain='secure.centrumfaktur.pl'):
        self.consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)
        self.access_token = oauth.OAuthToken(access_token_key, access_token_secret)
        self.invoicible_domain = invoicible_domain

        self.connection = httplib.HTTPSConnection(self.invoicible_domain)
        self.protocol = 'https'

        self.signature_method_hmac_sha1 = oauth.OAuthSignatureMethod_HMAC_SHA1()
        self.json_encoder = simplejson.JSONEncoder()

    def get_resources(self, path, query=None):
        query = query or {}
        query['format'] = 'json'
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            token=self.access_token,
            http_method="GET",
            http_url=urlparse.urlunparse((self.protocol, self.invoicible_domain, path, None, None, None)),
            parameters = query,
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, self.access_token)
        self.connection.request('GET',
            path + '?' + urllib.urlencode(query),
            headers=oauth_request.to_header()
        )
        response = self.connection.getresponse()
        json = response.read()
        if response.status != 200:
            raise DoesNotExists()
        return simplejson.loads(json)

    def create_resource(self, path, data):
        query = 'format=json'
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            token=self.access_token,
            http_method="POST",
            http_url=urlparse.urlunparse((self.protocol, self.invoicible_domain, path, query, None, None))
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, self.access_token)
        data = self.json_encoder.encode(data)
        headers = oauth_request.to_header()
        headers['Content-Type'] = 'application/json'
        headers['Accept'] = 'application/json'
        self.connection.request('POST',
            path,
            body=data,
            headers=headers
        )
        response = self.connection.getresponse()
        json = response.read()
        #print json
        if response.status != 200:
            raise ValidationError(response)
        return simplejson.loads(json)

    def update_resource(self, path, data):
        query = 'format=json'
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            token=self.access_token,
            http_method="PUT",
            http_url=urlparse.urlunparse((self.protocol, self.invoicible_domain, path, query, None, None))
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, self.access_token)
        data = self.json_encoder.encode(data)
        headers = oauth_request.to_header()
        headers['Content-Type'] = 'application/json'
        self.connection.request('PUT',
            path,
            body=data,
            headers=headers
        )
        response = self.connection.getresponse()
        return simplejson.loads(response.read())

    def delete_resource(self, path):
        query = 'format=json'
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            token=self.access_token,
            http_method="DELETE",
            http_url=urlparse.urlunparse((self.protocol, self.invoicible_domain, path, query, None, None))
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, self.access_token)
        self.connection.request('DELETE',
            path,
            headers=oauth_request.to_header()
        )
        response = self.connection.getresponse()
        return response.status == DELETED

class InvoicibleApiObjectField(object):
    def __init__(self, prepopulate_from, klass):
        self.prepopulate_from = prepopulate_from
        self.klass = klass
        self.name = '_' + prepopulate_from[:-4]

    def __get__(self, api_object, api_class):
        resource = api_object._client.get_resources(getattr(api_object, self.prepopulate_from))
        if not api_object.__dict__.get(self.name, None):
            resource = api_object._client.get_resources(getattr(api_object, self.prepopulate_from))
            api_object.__dict__[self.name] = self.klass(api_object._client, resource)
        return api_object.__dict__[self.name]

    def __set__(self, api_object, value):
        if not hasattr(api_object, 'resource_uri') or not getattr(api_object, 'resource_uri', None) \
          or not isinstance(value, self.klass):
            raise Exception("You can assign only saved %s instances." % self.klass.__name__)
        setattr(api_object, self.prepopulate_from, value.resource_uri)
        api_object.__dict__[self.name] = value

class InvoicibleApiManagerField(object):
    def __init__(self, prepopulate_from, manager_klass):
        self.prepopulate_from = prepopulate_from
        self.manager_klass = manager_klass
        self.name = '_' + prepopulate_from[:-4]

    def __get__(self, api_object, api_class):
        if not api_object.__dict__.get(self.name, None):
            resources_uri = getattr(api_object, self.prepopulate_from)
            manager = self.manager_klass(invoicible_client=api_object._client, resources_uri=resources_uri)
            api_object.__dict__[self.name] = manager
        return api_object.__dict__[self.name]

    def __set__(self, api_object, value):
        raise Exception("""You can't assign to this field: You can only iterate through it's content by all() method
and create items with create() method""")

class InvoicibleApiObject(object):
    _resources_uri = None
    _fields = {}

    def __init__(self, invoicible_client=None, resource_uri=None, json=None, **kwargs):
        self._client = invoicible_client
        if resource_uri:
            self.resource_uri = resource_uri
            json = self._client.get_resources(self.resource_uri)
        else:
            self.resource_uri = None

        if json:
            self.parse_json(json)

    def get_json(self):
        data = {}
        for f, t in self._fields.items():
            # getting field value
            try:
                field = getattr(self, f)
            except AttributeError:
                # maybe if it's required field it should raise an exception?
                break
            if t is datetime.datetime:
                data[f] = field.strftime(DATETIME_FORMAT)
            elif t is datetime.date:
                data[f] = field.strftime(DATE_FORMAT)
            elif t is ItemList:
                data[f] = map(lambda item: item.get_json(), field)
            elif not isinstance(field, InvoicibleApiObject) \
              and (not isinstance(field, type) or not issubclass(field, InvoicibleApiObject)):
                data[f] = field
        return data

    def parse_json(self, data, raw_json = False):
        if raw_json:
            data = simplejson.loads(data)
        data = self._parse_json(data)
        for f in data.keys():
            setattr(self, f, data[f])

    def _parse_json(self, data):
        d = {}
        if not isinstance(data, dict):
            raise ValidationError(u'Incorrect data type, expected dict, received: %s.' % type(data))
        for f, t in self._fields.items():
            try:
                field = data[f]
            except KeyError:
                if DEBUG:
                    print 'missing key', f
                continue
            try:
                if t is datetime.datetime:
                    value = datetime.datetime.strptime(field, DATETIME_FORMAT)
                elif t is datetime.date:
                    value = datetime.datetime.strptime(field, DATE_FORMAT)
                elif issubclass(t, list) and hasattr(t, 'item_klass'):
                    value = map(lambda item: t.item_klass(**item), field)
                else:
                    value = t(field)
            except Exception, e:
                raise ValidationError('Incorrect type for %s: %s (%s)' % ( self.__class__.__name__, f, e))
            d[f] = value
        return d

    def delete(self):
        if not self.resource_uri:
            raise Exception("Can delete object without resource_uri assigned.")
        resource = self._client.delete_resource(self.resource_uri)

    def save(self):
        if self.resource_uri:
            data = self._client.update_resource(self.resource_uri, self.get_json())
        else:
            if not hasattr(self, '_resources_uri') or not self._resources_uri:
                raise Exception(
                    "This object can't be saved it doesn't contains resources_uri! How did you get it??"
                )
            data = self._client.create_resource(self._resources_uri, self.get_json())
        self.parse_json(data)

    def __str__(self):
        return str(self.get_json())

    def __repr__(self):
        return str(self.get_json())

class InvoicibleApiObjectManager(object):
    api_klass = None
    _resources_uri = None

    def __init__(self, invoicible_client, resources_uri=None):
        self._client = invoicible_client
        self._resources_uri = resources_uri or self._resources_uri or self.api_klass._resources_uri

    def all(self, invoicible_client=None):
        result = []
        resources = self._client.get_resources(self._resources_uri)
        for resource in resources:
            result.append(self.api_klass(self._client, json=resource))
        return result

    def list(self, offset=0, limit=20):
        result = []
        resources = self._client.get_resources(self._resources_uri,
            query={'offset': offset, 'limit': limit})
        for resource in resources:
            result.append(self.api_klass(self._client, json=resource))
        return result

    def create(self, **kwargs):
        resource = self._client.create_resource(self._resources_uri, kwargs)
        return self.api_klass(self._client, json=resource)

class Customer(InvoicibleApiObject):
    _resources_uri = '/api/1.0/customers/'
    _fields = {
        'address': unicode,
        'contact': unicode,
        'email': unicode,
        'name': unicode,
        'resource_uri': unicode,
        'tax_id': unicode,
    }

class CustomerManager(InvoicibleApiObjectManager):
    api_klass = Customer

class Comment(InvoicibleApiObject):
    _fields = {
        'body': unicode,
        'summary': unicode,
    }

class CommentManager(InvoicibleApiObjectManager):
    api_klass = Comment

class Item(object):
    _fields = {
        'amount': unicode,
        'description': unicode,
        'product_id': unicode,
        'tax_rate': unicode,
        'unit': unicode,
        'unit_price': unicode,
    }

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, self._fields[key](value))

    def get_json(self):
        result = {}
        for key in self._fields.keys():
            result[key] = getattr(self, key, None)
        return result

    def __unicode__(self):
        return str(self.get_json())

    def __repr__(self):
        return str(self.get_json())

class ItemList(list):
    item_klass = Item

class Invoice(InvoicibleApiObject):
    _resources_uri = '/api/1.0/invoices/'
    _fields = {
        'advance_amount': unicode,
        'comments_uri': unicode,
        'currency_symbol': unicode,
        'customer_address': unicode,
        'customer_name': unicode,
        'customer_tax_id': unicode,
        'customer_uri': unicode,
        'date': datetime.date,
        'date_raised': datetime.date,
        'invoice_id': unicode,
        'invoice_type': unicode,
        'items': ItemList,
        'language': unicode,
        'paid_so_far': unicode,
        'payment_due': unicode,
        'resource_uri': unicode,
        'status': unicode,
        'summary': unicode,
    }
    customer = InvoicibleApiObjectField('customer_uri', Customer)
    comments = InvoicibleApiManagerField('comments_uri', CommentManager)

class InvoiceManager(InvoicibleApiObjectManager):
    api_klass = Invoice

class Estimate(InvoicibleApiObject):
    _resources_uri = '/api/1.0/estimates/'
    _fields = {
        'currency_symbol': unicode,
        'customer_uri': unicode,
        'comments_uri': unicode,
        'items': ItemList,
        'summary': unicode,
        'status': unicode,
    }
    customer = InvoicibleApiObjectField('customer_uri', Customer)
    comments = InvoicibleApiManagerField('comments_uri', CommentManager)

class EstimateManager(InvoicibleApiObjectManager):
    api_klass = Estimate
