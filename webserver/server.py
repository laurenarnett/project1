#!/usr/bin/env python2.7
import os
import datetime
import re
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, session

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
  cursor = g.conn.execute("SELECT * FROM recipes ORDER BY date_published DESC")
  recipes = []
  for result in cursor:
    recipes.append(result)
  cursor.close()
  context['recipes'] = recipes

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['logged_in_as'] = username
    # get subscription feed
    cursor = g.conn.execute(
      "SELECT r.* FROM recipes r, subscriptions s \
      WHERE s.subscriber_username='{}' \
      AND s.subscribee_username=r.publisher_username \
      AND (s.subscription_type='all' or s.subscription_type='on publish recipe') \
      ORDER BY date_published DESC;".format(username)
    )
    subscription_feed = []
    # filter out dietary restriction
    cursor2 = g.conn.execute("SELECT dietary_restriction FROM users WHERE username='{}'".format(username))
    dietary_restriction = cursor2.fetchone()['dietary_restriction']
    cursor2.close()
    for result in cursor:
      if (dietary_restriction == 'vegan' and result['dietary_restriction'] != 'vegan') \
        or (dietary_restriction == 'vegetarian' and result['dietary_restriction'] == 'none'):
        continue
      subscription_feed.append(result)
    cursor.close()

    context['subscription_feed'] = subscription_feed
    # remove duplicates in recipes
    context['recipes'] = [recipe for recipe in context['recipes'] if recipe not in subscription_feed]

  return render_template("index.html", **context)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
  if request.method == 'POST':
    name = request.form['name']
    username = request.form['username']
    password = request.form['password']
    email = request.form['email']
    dietary_restriction = request.form['dietary_restriction']
    zipcode = request.form['zipcode']
    # check if username exists
    cursor = g.conn.execute("SELECT username FROM users WHERE username='{}';".format(username))
    if cursor.rowcount != 0:
      return render_template("signup.html", error="Signup fail. Username already exists.")
    cursor.close()
    # check if dietary_restriction is valid
    if dietary_restriction not in set(['none', 'vegan', 'vegetarian']):
      return render_template("signup.html", error="Signup fail. Invalid dietary restriction.")
    # check if email is valid
    if not re.match(r"[a-zA-Z0-9._\-+]+@[A-Za-z0-9-]+\.[a-z]+", email):
      return render_template("signup.html", error="Signup fail. Invalid email.")
    # check if zipcode is valid
    if not zipcode.isdigit() or len(zipcode) > 5:
      return render_template("signup.html", error="Signup fail. Invalid zipcode.")

    # sign up and login
    g.conn.execute(
      "INSERT INTO users(name, username, email, password, dietary_restriction, zip_code)\
       values ('{}','{}','{}','{}','{}','{}');".format(\
        name, username, email, password, dietary_restriction, zipcode)
    )
    session['logged_in_as'] = username
    return redirect("/")
  else:
    return render_template("signup.html")

@app.route('/login', methods=['GET', 'POST'])
def login():
  if request.method == 'POST':
    username = request.form['username']
    password = request.form['password']
    cursor = g.conn.execute("SELECT username, password FROM users WHERE username='{}' and password='{}';".format(username, password))
    if cursor.rowcount == 0:
      return render_template("login.html", error="Login fail. Please try again.")
    cursor.close()

    # log in
    session['logged_in_as'] = username
    return redirect("/")
  else:
    return render_template("login.html")

@app.route('/logout')
def logout():
  del session['logged_in_as']
  return redirect("/")


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

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['username'] = username
    cursor = g.conn.execute("SELECT subscribee_username FROM subscriptions subs\
            WHERE subscriber_username = '{}' and subscribee_username\
            = '{}'".format(username, user_info.username))
    result = cursor.fetchone()
    cursor.close()
    context['subs'] = result 

  context['user_info'] = user_info
  context['recipes'] = recipes
  context['bookmarks'] = bookmarks

  return render_template("profile.html", **context)

@app.route('/account_settings/<name>')
def account_settings(name):
  # verify username is same as login information
  if session.get("logged_in_as"):
    username = session.get("logged_in_as")
    if username != name:
      return redirect("/")
  context = dict()

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['logged_in_as'] = username

  # get subscriptions
  subs = []
  cursor = g.conn.execute(("SELECT * FROM subscriptions WHERE\
    subscriber_username = '{}'").format(name))
  for result in cursor:
    subs.append(result)
  cursor.close()
  # get bookmarks
  books = []
  cursor = g.conn.execute(("SELECT * FROM bookmarks WHERE\
    username = '{}'").format(name))
  for result in cursor:
    books.append(result)
  cursor.close()

  context['subs'] = subs
  context['books'] = books
  return render_template('account_settings.html', **context)


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
            r.recipe_name=rev.recipe_name WHERE r.recipe_name = '"
            + name.replace("_", " ") + 
            "' ORDER BY date_published DESC")
  reviews = []
  for result in cursor:
      reviews.append(result)
  cursor.close()

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['logged_in_as'] = username

    # get subscriptions
    cursor = g.conn.execute("SELECT subscribee_username FROM subscriptions\
            WHERE subscriber_username = '{}' and subscribee_username\
            = '{}'".format(username, recipe_data.publisher_username))
    result = cursor.fetchone()
    cursor.close()
    context['subs'] = result 
    
    # get bookmarks
    cursor = g.conn.execute("SELECT recipe_name FROM bookmarks\
            WHERE username='{}' and recipe_name\
            = '{}'".format(username, recipe_data.recipe_name))
    result = cursor.fetchone()
    context['bookmarks'] = result
    cursor.close()


  context['recipe_data'] = recipe_data
  context['ingredients_data'] = ingredients_data
  context['reviews'] = reviews

  return render_template('recipe_page.html', **context)

@app.route('/subscribe', methods=['POST'])
def addsubscription():
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    subscribee_username = request.form.get('author_username')
    sub_type = request.form.get('subscription_type')

    # add to subscriptions table
    g.conn.execute(
      "INSERT INTO subscriptions(subscriber_username, subscribee_username, subscription_type)\
       values ('{}','{}','{}');".format(username, subscribee_username, sub_type)
    )
    return redirect("/{}".format(request.form.get('loc')))
  else:
    return redirect("/signup")

@app.route('/bookmark', methods=['POST'])
def addbookmark():
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    recipe_name = request.form.get('recipe_name')

    # add to subscriptions table
    g.conn.execute(
      "INSERT INTO bookmarks(username, recipe_name)\
       values ('{}','{}');".format(username, recipe_name)
    )
    return redirect("/{}".format(request.form.get('loc')))
  else:
    return redirect("/signup")
  
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

@app.route('/remove_sub', methods=['POST'])
def removesub():
  if session.get("logged_in_as"):
    # get username
    subscriber_username = session.get("logged_in_as")
    subscribee_username = request.form.get('subscribee_username')

    # remove from subscriptions table
    g.conn.execute(
      "DELETE FROM subscriptions \
      WHERE subscriber_username = '{}' AND subscribee_username = '{}';"\
      .format(subscriber_username, subscribee_username)
    )
    return redirect("/{}".format(request.form.get('loc')))

@app.route('/remove_bookmark', methods=['POST'])
def removebookmark():
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    recipe_name = request.form.get('recipe_name')

    # remove from subscriptions table
    g.conn.execute(
      "DELETE FROM bookmarks\
      WHERE username = '{}' AND recipe_name = '{}';"\
      .format(username, recipe_name)
    )
    return redirect("/{}".format(request.form.get('loc')))
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
    app.secret_key = os.urandom(12)
    app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

  run()
