from tornado.options import define, options, parse_config_file


define("auth_name", default="apoptosis", help="Name of the authentication system")

define("redis_host", default="localhost", help="Redis server hostname")
define("redis_port", default=6379, help="Redis server port")
define("redis_database", default=0, help="Redis server database")
define("redis_password", default="", help="Redis server password")

define("database_uri", default="sqlite:////tmp/apoptosis.db", help="Database URI")

define("http_port", default=5000, help="HTTP Port")

define("tornado_secret", help="Tornado Secret")
define("tornado_translations", help="Tornado translations path")
define("tornado_templates", help="Tornado templates path")
define("tornado_static", help="Tornado static path")

define("evesso_clientid", help="EVE SSO client ID")
define("evesso_secretkey", help="EVE SSO secret key")
define("evesso_callback", help="EVE SSO callback URI")

options.define("slack_apitoken", help="Slack API Token")
options.define("slack_username", help="Slack username", default="apoptosis")

parse_config_file("/home/user/apoptosis.conf")  # XXX correct location

auth_name = options.auth_name

redis_host = options.redis_host
redis_port = options.redis_port
redis_database = options.redis_database
redis_password = options.redis_password

database_uri = options.database_uri

http_port = options.http_port

tornado_secret = options.tornado_secret
tornado_translations = options.tornado_translations
tornado_templates = options.tornado_templates
tornado_static = options.tornado_static

evesso_clientid = options.evesso_clientid
evesso_secretkey = options.evesso_secretkey
evesso_callback = options.evesso_callback

slack_apitoken = options.slack_apitoken
slack_username = options.slack_username
