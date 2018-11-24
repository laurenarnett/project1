#!/usr/bin/env python2.7
import os
import datetime
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)

DB_USER = "lba2138"
DB_PASSWORD = "t522wc1p"
DB_SERVER = "w4111.cisxo09blonu.us-east-1.rds.amazonaws.com"
DATABASEURI = "postgresql://"+DB_USER+":"+DB_PASSWORD+"@"+DB_SERVER+"/w4111"

engine = create_engine(DATABASEURI)

@app.before_request
def before_request():
  """
  This function is run at the beginning of every web request
  (every time you enter an address in the web browser).
  We use it to setup a database connection that can be used throughout the request

  The variable g is globally accessible
  """
  try:
    g.conn = engine.connect()
  except:
    print "uh oh, problem connecting to database"
    import traceback; traceback.print_exc()
    g.conn = None

@app.teardown_request
def teardown_request(exception):
  """
  At the end of the web request, this makes sure to close the database connection.
  If you don't the database could run out of memory!
  """
  try:
    g.conn.close()
  except Exception as e:
    pass

@app.route('/')
def index():
  """
  request is a special object that Flask provides to access web request information:

  request.method:   "GET" or "POST"
  request.form:     if the browser submitted a form, this contains the data in the form
  request.args:     dictionary of URL arguments e.g., {a:1, b:2} for http://localhost?a=1&b=2

  See its API: http://flask.pocoo.org/docs/0.10/api/#incoming-request-data
  """
  context = dict()

  cursor = g.conn.execute("SELECT * from recipes")
  recipes = []
  for result in cursor:
    recipes.append(result)
  cursor.close()
  context['recipes'] = recipes

  return render_template("index.html", **context)


@app.route('/profile/<name>')
def profile(name):
  context = dict()

  # get user information
  cursor = g.conn.execute("SELECT name,username FROM users WHERE username='" + name + "'")
  user_info = cursor.fetchone()
  cursor.close()
  
  # get recipes this user has published
  cursor = g.conn.execute("SELECT * FROM recipes WHERE publisher_username='" + name + "'")
  recipes = []
  for result in cursor:
      recipes.append(result)
  cursor.close()

  cursor = g.conn.execute("SELECT r.* FROM recipes r INNER JOIN bookmarks b\
                            ON r.recipe_name = b.recipe_name WHERE b.username='" + name + "'")
  bookmarks = []
  for result in cursor:
      bookmarks.append(result)
  cursor.close()

  context['user_info'] = user_info
  context['recipes'] = recipes
  context['bookmarks'] = bookmarks

  return render_template("profile.html", **context)


@app.route('/recipe_page/<name>')
def recipe_page(name):
  context = dict()

  # get recipe data
  cursor = g.conn.execute("SELECT * from recipes WHERE recipe_name = '" + name.replace("_", " ") + "'")
  recipe_data = cursor.fetchone()
  cursor.close()

  # get ingredients data
  cursor = g.conn.execute("SELECT l.*\
            from ingredients_list l inner join recipes r on\
            r.recipe_name=l.recipe_name WHERE r.recipe_name = '" + name.replace("_", " ") + "'")  
  ingredients_data = []
  for result in cursor:
    ingredients_data.append(result)
  cursor.close()
  
  # get reviews data
  cursor = g.conn.execute("SELECT rev.* FROM reviews rev \
            INNER JOIN recipes r on\
            r.recipe_name=rev.recipe_name WHERE r.recipe_name = '" + name.replace("_", " ") + "'")  
  reviews = []
  for result in cursor:
      reviews.append(result)
  cursor.close()

  context['recipe_data'] = recipe_data
  context['ingredients_data'] = ingredients_data
  context['reviews'] = reviews

  return render_template('recipe_page.html', **context)

@app.route('/addreview', methods=['POST'])
def addreview():
  review = request.form['review']
  rating = request.form['rating']
  author_username = request.form['author_username']
  recipe_name = request.form['recipe_name']
  date_published = datetime.datetime.today().strftime('%Y-%m-%d')

  cmd = "INSERT INTO reviews VALUES ('" \
            + review + "'," + str(rating) + ",'" + date_published + "','"\
            + author_username + "','" + recipe_name + "')"
  g.conn.execute(text(cmd))
  return redirect('/recipe_page/' + recipe_name.replace(" ", "_"))


if __name__ == "__main__":
  import click

  @click.command()
  @click.option('--debug', is_flag=True)
  @click.option('--threaded', is_flag=True)
  @click.argument('HOST', default='0.0.0.0')
  @click.argument('PORT', default=8111, type=int)
  def run(debug, threaded, host, port):
    HOST, PORT = host, port
    print "running on %s:%d" % (HOST, PORT)
    app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

  run()
