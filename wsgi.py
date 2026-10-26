import sys
import os

path = '/home/minphet/EpeMDB'
if path not in sys.path:
    sys.path.insert(0, path)

os.environ['TMDB_API_KEY'] = 'a12755aeb47f96a7cd5862a1a3544124'

from app import app
from a2wsgi import ASGIMiddleware
application = ASGIMiddleware(app)