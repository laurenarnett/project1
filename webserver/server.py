#!/usr/bin/env python2.7
import os
import datetime
import re
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, session, flash

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
    query = text("SELECT r.* FROM recipes r, subscriptions s \
            WHERE s.subscriber_username=:username \
            AND s.subscribee_username=r.publisher_username \
            AND (s.subscription_type='all' or s.subscription_type='on publish recipe') \
            ORDER BY date_published DESC;")
    cursor = g.conn.execute(query, username=username)
    subscription_feed = []
    # filter out dietary restriction
    query2 = text("SELECT dietary_restriction FROM users WHERE username=:username;")
    cursor2 = g.conn.execute(query2, username=username)
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
    query = text("SELECT username FROM users WHERE username=:username;")
    cursor = g.conn.execute(query, username=username)
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
    query = text("INSERT INTO users(name, username, email, password, dietary_restriction, zip_code)\
       values (:name, :username, :email, :password, :dietary_restriction, :zipcode);")
    g.conn.execute(query,
        name=name, username=username, email=email, password=password,
        dietary_restriction=dietary_restriction, zipcode=zipcode
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
    query = text("SELECT username, password FROM users WHERE username=:username and password=:password;")
    cursor = g.conn.execute(query, username=username, password=password)
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
  query = text("SELECT name, username FROM users WHERE username=:username;")
  cursor = g.conn.execute(query, username=name)
  user_info = cursor.fetchone()
  cursor.close()

  # get recipes this user has published
  query = text("SELECT * FROM recipes WHERE publisher_username=:username;")
  cursor = g.conn.execute(query, username=name)
  recipes = []
  for result in cursor:
      recipes.append(result)
  cursor.close()

  query = text("SELECT r.* FROM recipes r INNER JOIN bookmarks b \
              ON r.recipe_name = b.recipe_name WHERE b.username=:username;")
  cursor = g.conn.execute(query, username=name)
  bookmarks = []
  for result in cursor:
      bookmarks.append(result)
  cursor.close()

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['username'] = username
    query = text("SELECT subscribee_username FROM subscriptions subs\
            WHERE subscriber_username=:username and subscribee_username=:other_username;")
    cursor = g.conn.execute(query, username=username, other_username=user_info.username)
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
    context['logged_in_as'] = username

    # get subscriptions
    subs = []
    query = text("SELECT * FROM subscriptions WHERE subscriber_username=:username;")
    cursor = g.conn.execute(query, username=name)
    for result in cursor:
      subs.append(result)
    cursor.close()
    # get bookmarks
    books = []
    query = text("SELECT * FROM bookmarks WHERE username=:username;")
    cursor = g.conn.execute(query, username=name)
    for result in cursor:
      books.append(result)
    cursor.close()

    # get published recipes
    recipes=[]
    query = text("SELECT * FROM recipes WHERE publisher_username=:username;")
    cursor = g.conn.execute(query, username=name)
    for result in cursor:
      recipes.append(result)
    cursor.close

    context['subs'] = subs
    context['books'] = books
    context['recipes'] = recipes

    return render_template('account_settings.html', **context)
  else:
    return redirect('/login')


@app.route('/recipe_page/<name>')
def recipe_page(name):
  context = dict()
  context['conversions'] = dict()

  # get recipe data
  query = text("SELECT * FROM recipes WHERE recipe_name=:recipe_name;")
  cursor = g.conn.execute(query, recipe_name=name.replace("_", " "))
  recipe_data = cursor.fetchone()
  cursor.close()

  # get ingredients data
  query = text("SELECT l.* FROM ingredients_list l INNER JOIN recipes r on\
                r.recipe_name=l.recipe_name WHERE r.recipe_name=:recipe_name;")
  cursor = g.conn.execute(query, recipe_name=name.replace("_", " "))
  ingredients_data = []
  for result in cursor:
    ingredients_data.append(result)

    # count has no valid conversions
    if result.unit == 'count':
        continue

    # make vaild conversions for this ingredient
    ingredient_name = result.ingredient_name
    unit = result.unit
    quantity = result.quantity
    conversions_list = []
    convert_cursor = g.conn.execute(text("SELECT c.*, " + str(quantity) + "* c.multiplier AS res \
        FROM conversions c WHERE\
        ingredient_name LIKE (CASE WHEN ('" + ingredient_name + "' = 'water' OR '" + ingredient_name\
        + "' = 'flour' OR '" + ingredient_name + "' = 'sugar' OR '" + ingredient_name + "' = 'butter')\
        THEN '" + ingredient_name + "' ELSE '\%' END) AND from_unit = '" + unit.split('s')[0] + "'"))
    for convert_result in convert_cursor:
        conversions_list.append(convert_result)
    context['conversions'][ingredient_name] = conversions_list
    convert_cursor.close()
  cursor.close()

  # get reviews data
  query = text(
    "SELECT rev.* FROM reviews rev, recipes r\
    WHERE r.recipe_name=rev.recipe_name and r.recipe_name=:recipe_name\
    ORDER BY date_published DESC;"
  )
  cursor = g.conn.execute(query, recipe_name=name.replace("_", " "))
  reviews = []
  for result in cursor:
      reviews.append(result)
  cursor.close()

  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    context['logged_in_as'] = username

    # get subscriptions
    query = text("SELECT subscribee_username FROM subscriptions\
                  WHERE subscriber_username=:username and subscribee_username\
                  =:other_username;")
    cursor = g.conn.execute(query, username=username, other_username=recipe_data.publisher_username)
    result = cursor.fetchone()
    cursor.close()
    context['subs'] = result

    # get bookmarks
    query = text("SELECT recipe_name FROM bookmarks WHERE username=:username and recipe_name=:recipe_name;")
    cursor = g.conn.execute(query, username=username, recipe_name=recipe_data.recipe_name)
    result = cursor.fetchone()
    context['bookmarks'] = result
    cursor.close()


  context['recipe_data'] = recipe_data
  context['ingredients_data'] = ingredients_data
  context['reviews'] = reviews

  return render_template('recipe_page.html', **context)

@app.route('/subscribe', methods=['POST'])
def subscription():
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    subscribe_activity = request.form.get('subscribe_activity')
    if subscribe_activity == "Add":
      subscribee_username = request.form.get('author_username')
      sub_type = request.form.get('subscription_type')
      # add to subscriptions table
      query = text("INSERT INTO subscriptions(subscriber_username, subscribee_username, subscription_type)\
                    VALUES (:username, :subscribee_username, :sub_type);")
      g.conn.execute(query, username=username, subscribee_username=subscribee_username, sub_type=sub_type)
      return redirect("/{}".format(request.form.get('loc')))
    elif subscribe_activity == "Remove":
      subscribee_username = request.form.get('subscribee_username')

      # remove from subscriptions table
      query = text("DELETE FROM subscriptions WHERE subscriber_username=:username AND subscribee_username=:subscribee_username;")
      g.conn.execute(query, username=username, subscribee_username=subscribee_username)

      return redirect("/{}".format(request.form.get('loc')))
  else:
    return redirect("/signup")

@app.route('/bookmark', methods=['POST'])
def addbookmark():
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    recipe_name = request.form.get('recipe_name')
    bookmark_activity = request.form.get('bookmark_activity')
    if bookmark_activity == "Add":

      # add to subscriptions table
      query = text("INSERT INTO bookmarks(username, recipe_name)\
                    VALUES (:username, :recipe_name);")
      g.conn.execute(query, username=username, recipe_name=recipe_name)
      return redirect("/{}".format(request.form.get('loc')))

    elif bookmark_activity =="Remove":
      # remove from subscriptions table
      query = text("DELETE FROM bookmarks WHERE username=:username AND recipe_name=:recipe_name;")
      g.conn.execute(query, username=username, recipe_name=recipe_name)
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

  if len(rating) == 0 or len(review) == 0:
    flash("Please making sure you have a rating and review before posting.")
    return redirect('/recipe_page/' + recipe_name.replace(" ", "_"))

  query = text("SELECT * FROM reviews WHERE author_username=:author_username AND recipe_name=:recipe_name;")
  res = g.conn.execute(query, author_username=author_username, recipe_name=recipe_name)\
    .fetchone()
  if res != None:
    flash("You have already posted a review on this recipe.")
    return redirect('/recipe_page/' + recipe_name.replace(" ", "_"))


  query = text("INSERT INTO reviews VALUES (:review, :rating, :date_published, :author_username, :recipe_name);")
  g.conn.execute(query, review=review, rating=str(rating), date_published=date_published,
                author_username=author_username, recipe_name=recipe_name)
  return redirect('/recipe_page/' + recipe_name.replace(" ", "_"))

@app.route('/delete_recipe',methods=['POST'])
def deleterecipe():
  recipe_name = request.form['recipe_name']
  if session.get("logged_in_as"):
    # get username
    username = session.get("logged_in_as")
    if username == request.form['username']:
      query = text("DELETE FROM recipes WHERE recipe_name=:recipe_name and\
      publisher_username=:publisher_username;")
      g.conn.execute(query, recipe_name=recipe_name, publisher_username=username)
      return redirect('/{}'.format(request.form['loc']))
  else:
    return redirect('/login')

@app.route("/publish", methods=['GET', 'POST'])
def publish():
  if not session.get('logged_in_as'):
    return render_template('publish.html', error="Please sign in to publish a recipe.")

  context = dict()
  context['logged_in_as'] = session.get('logged_in_as')
  cursor = g.conn.execute("SELECT * FROM ingredients order by name;")
  all_ingredients = []
  for result in cursor:
    if result['name'] == '%':
      continue
    all_ingredients.append(result)
  cursor.close()
  context['ingredients'] = all_ingredients
  if request.method == 'POST':
    recipe_name = request.form['recipe_name']
    cuisine_type = request.form['cuisine_type']
    meal_type = request.form['meal_type']
    dietary_restriction = request.form['dietary_restriction']
    ingredients = request.form.getlist('ingredients[]')
    units = request.form.getlist('units[]')
    quantities = request.form.getlist('quantities[]')
    # verify arrays are all same length
    if len(ingredients) != len(units) or len(units) != len(quantities) or len(ingredients) != len(quantities):
      context['error'] = "Please populate the ingredient name, units, and quantities for each ingredient."
      return render_template('publish.html', **context)
    # verify quantities are all floats
    if not all([q.replace('.','',1).isdigit() for q in quantities]):
      context['error'] = "Please specify float (i.e. decimal number) quantities for each ingredient."
      return render_template('publish.html', **context)
    # verify recipe name doesn't already exist
    query = text("SELECT * FROM recipes WHERE recipe_name=:recipe_name;")
    cursor = g.conn.execute(query, recipe_name=recipe_name)
    if cursor.rowcount != 0:
      context['error'] = "Recipe name already exists. Please choose another."
      return render_template('publish.html', **context)
    # verify all ingredients exist
    all_ingredient_names = set([ingredient['name'] for ingredient in all_ingredients])
    nonexistent_ingredients = [ing for ing in ingredients if ing not in all_ingredient_names]
    if len(nonexistent_ingredients) != 0:
      context['error'] = "You entered a non-existent ingredient. Please add it to the registry."
      return render_template('publish.html', **context)
    # verify meal type
    if meal_type not in set(['breakfast', 'lunch', 'dinner', 'snack', 'dessert']):
      context['error'] = "Invalid meal type."
      return render_template('publish.html', **context)
    # verify dietary restriction
    if dietary_restriction not in set(['none', 'vegan', 'vegetarian']):
      context['error'] = "Invalid dietary restriction."
      return render_template('publish.html', **context)
    # insert recipe
    date_published = datetime.datetime.today().strftime('%Y-%m-%d')
    query = text("INSERT INTO recipes(recipe_name, cuisine_type, meal_type, dietary_restriction, date_published, publisher_username) \
            VALUES (:recipe_name, :cuisine_type, :meal_type, :dietary_restriction, :date_published, :publisher_username);")
    g.conn.execute(query,
      recipe_name=recipe_name, cuisine_type=cuisine_type, meal_type=meal_type,
      dietary_restriction=dietary_restriction, date_published=date_published,
      publisher_username=session.get('logged_in_as')
    )

    # insert ingredients_list
    for ing, unit, quantity in zip(ingredients, units, quantities):
      if ingredients == "":
        continue
      query = text("INSERT INTO ingredients_list(unit, quantity, recipe_name, ingredient_name)\
        VALUES (:unit, :quantity, :recipe_name, :ing);")
      g.conn.execute(query, unit=unit, quantity=quantity, recipe_name=recipe_name, ing=ing)
    # redirect to recipe page
    return redirect('/recipe_page/'+recipe_name.replace(" ", "_"))
  else:
    return render_template('publish.html', **context)

@app.route("/ingredients", methods=['GET', 'POST'])
def ingredients():
  if request.method == 'POST':
    # redirect to ingredients page
    name = request.form['ingredient_name']
    food_type = request.form['food_type']
    # check that name isn't already taken
    query = text("SELECT * FROM ingredients WHERE name=:name;")
    cursor = g.conn.execute(query, name=name)
    if cursor.rowcount != 0:
      return redirect('/ingredients')

    # insert
    query = text("INSERT INTO ingredients(name, food_type) VALUES (:name, :food_type);")
    g.conn.execute(query, name=name, food_type=food_type)
    return redirect('/ingredients')
  else:
    cursor = g.conn.execute("SELECT * FROM ingredients order by name;")
    ingredients = []
    for result in cursor:
      if result['name'] == '%':
        continue
      ingredients.append(result)
    cursor.close()
    return render_template('ingredients.html', ingredients=ingredients, logged_in_as=session.get('logged_in_as'))

@app.route("/search")
def search():
  query = request.args['query']
  cursor = g.conn.execute(
    text("SELECT * FROM recipes WHERE LOWER(recipe_name) LIKE CONCAT('%', :query, '%');"),
    query=query.lower()
  )
  context = dict()
  recipes = []
  for result in cursor:
    recipes.append(result)
  cursor.close()
  context['recipes'] = recipes
  context['logged_in_as'] = session.get('logged_in_as')
  return render_template('search.html', **context)

@app.route("/update",methods=["POST"])
def update():
    logged_in_as = session.get('logged_in_as')
    if request.form.get('full_name'):
        full_name = request.form.get('full_name')
        query = text("UPDATE users SET name = (:full_name) WHERE\
                username=(:logged_in_as);")
        g.conn.execute(query, full_name=full_name, logged_in_as=logged_in_as)
        return redirect("/{}".format(request.form.get('loc')))
    if request.form.get('password'):
        password = request.form.get('password')
        query = text("UPDATE users SET password = (:password) WHERE\
                username=(:logged_in_as);")
        g.conn.execute(query, password=password, logged_in_as=logged_in_as)
        return redirect("/{}".format(request.form.get('loc')))
    if request.form.get('email'):
        email= request.form.get('email')
        query = text("UPDATE users SET email = (:email) WHERE\
                username=(:logged_in_as);")
        g.conn.execute(query, email=email, logged_in_as=logged_in_as)
        return redirect("/{}".format(request.form.get('loc')))
    if request.form.get('zipcode'):
        zipcode = request.form.get('zipcode')
        query = text("UPDATE users SET zip_code = (:zipcode) WHERE\
                username=(:logged_in_as);")
        g.conn.execute(query, zipcode=zipcode, logged_in_as=logged_in_as)
        return redirect("/{}".format(request.form.get('loc')))
    if request.form.get('diet'):
        diet = request.form.get('diet')
        query = text("UPDATE users SET dietary_restriction = (:diet) WHERE\
                username=(:logged_in_as);")
        g.conn.execute(query, diet=diet, logged_in_as=logged_in_as)
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
