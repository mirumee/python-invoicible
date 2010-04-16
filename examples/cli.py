import cmd
import copy
import httplib
import oauth.oauth as oauth
import pprint
import readline
import sys
import urlparse
import webbrowser

import invoicible

# key and secret granted by the service provider for this consumer application
CONSUMER_KEY = ''
CONSUMER_SECRET = ''

# access token for this consumer application which allows access to user resources
ACCESS_TOKEN_KEY = ''
ACCESS_TOKEN_SECRET = ''

COMPANY_DOMAIN = ''

def ask(question):
    while True:
        result = raw_input(question)
        if result.lower() in ('y', 'yes', ''):
            return True
        elif result.lower() in ('n', 'no'):
            return False

class InvoicibleOAuthHelper(oauth.OAuthClient):
    """
    This is helper for oauth autorization, if you are going to create your own client
    you should check the logic of authorise method.
    """
    request_token_path = '/aplikacje/request/token/'
    access_token_path = '/aplikacje/access/token/'
    authorization_path = '/aplikacje/autoryzacja/'

    def __init__(self, consumer_key, consumer_secret, company_domain):
        self.company_domain = company_domain
        self.connection = httplib.HTTPConnection(self.company_domain)
        self.consumer = oauth.OAuthConsumer(consumer_key, consumer_secret)

        self.signature_method_hmac_sha1 = oauth.OAuthSignatureMethod_HMAC_SHA1()

    def authorise(self):
        request_token = self.fetch_request_token()
        verifier = self.authorise_token(request_token)
        access_token = self.fetch_access_token(verifier)
        return access_token

    def fetch_request_token(self):
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            http_url=urlparse.urlunparse(("http", self.company_domain, self.request_token_path, None, None, None))
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, None)
        self.connection.request(
            oauth_request.http_method,
            self.request_token_path,
            headers=oauth_request.to_header()
        )
        response = self.connection.getresponse()
        self._request_token = oauth.OAuthToken.from_string(response.read())
        return self._request_token

    def fetch_verifier(self, url):
        webbrowser.open_new(url)
        verifier = raw_input('Copy verifier which you should see on page after autorization:')
        return verifier

    def authorise_token(self, request_token):
        oauth_request = oauth.OAuthRequest.from_token_and_callback(
            token=request_token,
            http_url=urlparse.urlunparse(("http", self.company_domain, self.authorization_path, None, None, None))
        )
        self._verifier = self.fetch_verifier(oauth_request.to_url())
        return self._verifier

    def fetch_access_token(self, verifier=None):
        self._request_token.verifier = verifier
        oauth_request = oauth.OAuthRequest.from_consumer_and_token(
            self.consumer,
            token=self._request_token,
            http_url=urlparse.urlunparse(("http", self.company_domain, self.access_token_path, None, None, None))
        )
        oauth_request.sign_request(self.signature_method_hmac_sha1, self.consumer, self._request_token)
        self.connection.request(oauth_request.http_method, self.access_token_path, headers=oauth_request.to_header())

        response = self.connection.getresponse()
        self.access_token = oauth.OAuthToken.from_string(response.read())
        return self.access_token

class SimpleClientCommandLine(cmd.Cmd):
    """
    Really simple invoicible application. It allows to list and updates some resources through api.
    """
    def __init__(self, client, *args, **kwargs):
        self.client = client
        self.customer_manager = invoicible.CustomerManager(self.client)
        self.estimate_manager = invoicible.EstimateManager(self.client)
        self.invoice_manager = invoicible.InvoiceManager(self.client)

        self.prompt = "invoicible$ "
        self.intro = "\nThis is really simple invoicible api client. Type 'help' or '?' for usage hints.\n"
        #cmd.Cmd is old style class
        cmd.Cmd.__init__(self, *args, **kwargs)

    def do_help(self, *args):
        print "list"
        #print "create"
        print "delete"
        print "quit"

    def help_delete(self):
        print "delete resource_uri"

    def do_delete(self, line):
        args = line.split()
        if len(args) != 1:
            return self.help_delete()
        else:
            self.client.delete_resource(args[0])

    def help_list(self):
        print "list invoices|estimates|customers"

    def do_list(self, line):
        args = line.split()
        if len(args) != 1 or args[0] not in ['invoices', 'customers', 'estimates']:
            return self.help_list()

        if args[0] == 'customers':
            result = self.customer_manager.all()
        elif args[0] == 'estimates':
            result = self.estimate_manager.all()
        else:
            result = self.invoice_manager.all()

        pprint.pprint(result)

    def complete_list(self, line, *args):
        return [ command for command in ('invoices', 'customers', 'estimates') if command.startswith(line)]

    def do_EOF(self, line):
        print ""
        return 1
    do_quit = do_EOF

def run_example(consumer_key=CONSUMER_KEY, consumer_secret=CONSUMER_SECRET,
        access_token_key=ACCESS_TOKEN_KEY, access_token_secret=ACCESS_TOKEN_SECRET, company_domain=COMPANY_DOMAIN):
    if not consumer_key or not consumer_secret:
        print """
You have not provided application (oauth consumer) keys. Please search invoicible api
documentation for testing keys (or generate new ones for your application in invoivible service)
and put those values into this file (%s) as CONSUMER_KEY and CONSUMER_SECRET.
""" % (__file__)
        sys.exit(1)

    if not company_domain:
        company_domain = raw_input("Please provide company domain (and put it to this file as COMPANY_DOMAIN to prevent this step in future) which resources you want to access (for example: mycompany.centrumfaktur.pl): ")

    if not access_token_key and not access_token_secret:
        print """
You have not provided oauth access token which allows your application access given user resources.
If you have already those keys generated please put them into this file (%s) as ACCESS_TOKEN_KEY and
ACCESS_TOKEN_SECRET if not this application will help you generate those keys.
""" % (__file__)
        if not ask("Do you want to generate access token ([y]/n)?"):
            sys.exit(1)


        oauth_helper = InvoicibleOAuthHelper(consumer_key, consumer_secret, company_domain)
        access_token = oauth_helper.authorize()
        access_token_key, access_token_secret = access_token.key, access_token.secret
        print """
Please copy access token key: %s and access token secret: %s as ACCESS_TOKEN_KEY and ACCESS_TOKEN_SECRET
into this file (%s) so next time you will skip application autorization step.
""" % (access_token_key, access_token_secret, __file__)

    if not company_domain:
        company_domain = raw_input("Please provide company domain (and put it to this file as COMPANY_DOMAIN to prevent this step in future) which resources you want to access (for example: mycompany.centrumfaktur.pl): ")

    invoicible_client = invoicible.Client(
        consumer_key,
        consumer_secret,
        access_token_key,
        access_token_secret,
        invoicible_domain = company_domain,
    )
    command_line = SimpleClientCommandLine(invoicible_client)
    command_line.cmdloop()

if __name__ == "__main__":
    run_example()
