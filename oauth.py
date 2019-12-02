from flask import Flask, request, session, redirect, url_for
import requests
import json
import time

# spin up the flask server so we can oauth authenticate
def get_oauth(api_data):
    print('No tokens saved, please authorize the app by going to localhost:4200')

    app = Flask(__name__)

    # redirect to the static html page with the link
    @app.route('/')
    def main():
        return '<a href="https://www.bungie.net/en/oauth/authorize?client_id=' + api_data[
            'id'] + '&response_type=code&state=asdf">Click me to authorize the script</a>'


    def shutdown_server():
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()


    @app.route('/shutdown')
    def shutdown():
        shutdown_server()
        return 'Server shutting down...'


    # catch the oauth redirect
    @app.route('/redirect')
    def oauth_redirect():
        # get the token/refresh_token/expiration
        code = request.args.get('code')
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        params = {
            'grant_type': 'authorization_code',
            'client_id': api_data['id'],
            'client_secret': api_data['secret'],
            'code': code
        }
        r = requests.post('https://www.bungie.net/platform/app/oauth/token/', data=params, headers=headers)
        resp = r.json()

        # save refresh_token/expiration in token.json
        token = {
            'refresh': resp['refresh_token'],
            'expires': time.time() + resp['refresh_expires_in']
        }
        token_file = open('token.json', 'w')
        token_file.write(json.dumps(token))
        return '<a href="/shutdown">Click me to continue</a>'

    app.run(port=4200)
