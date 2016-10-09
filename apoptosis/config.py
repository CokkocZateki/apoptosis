from tornado.options import define, options, parse_config_file


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

options.define("ts3_server", help="Teamspeak 3 server")
options.define("ts3_port", default=10011, help="Teamspeak 3 port")
options.define("ts3_username", help="Teamspeak 3 username")
options.define("ts3_password", help="Teamspeak 3 password")

parse_config_file("/etc/apoptosis.conf")

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

ts3_server = options.ts3_server
ts3_port = options.ts3_port
ts3_username = options.ts3_username
ts3_password = options.ts3_password
