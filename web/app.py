import json
from flask import Flask, request, jsonify
from flask_restful import Resource, Api  # pip3 install flask-restful
import bcrypt
from pymongo import MongoClient

MONGO_DB_URL = "mongodb://db:27017"
USERNAME = "Username"
PASSWORD = "Password"
AMOUNT = "amount"
TO = "to"
BANK = "BANK"
FEE = 1
STATUS = "status code"
MESSAGE = "message"
OWN = "Own"
DEBT = "Debt"

app = Flask(__name__)
api = Api(app)

client = MongoClient(MONGO_DB_URL)
db = client.BankAPI  # database
users = db["Users"]  # collection


def generate_return_json(message: str, status: int) -> json:
    ret_map = {
        MESSAGE: message,
        STATUS: status,
    }
    return jsonify(ret_map)


def check_parameters(required_parameters: tuple, posted_data: dict) -> tuple:
    missing_parameters = ""
    for c in required_parameters:
        if c not in posted_data:
            missing_parameters += f"'{c}',"
    if len(missing_parameters) > 0:
        return False, generate_return_json(message=f"Parameters {missing_parameters} are missing", status=305)
    return True, None


def check_credentials(username: str, password: str = None) -> tuple:
    user = users.find_one({USERNAME: username}, {USERNAME: 1, PASSWORD: 1})
    if user is None:
        if password is None:  # function is called to check whether user exists
            return False, None  # it doesn't, can proceed with registration but not with transfer
        return False, generate_return_json(message=f"User {username} does not exist", status=305)

    # Next, user exists
    if password is None:  # function is called to check whether user exists...
        # ...it does, can proceed with transfer but not with registration
        return True, generate_return_json(message=f"User {username} already exists", status=301)

    # Otherwise, check the supplied password to complete credentials verification
    stored_hash = user[PASSWORD]
    if not bcrypt.checkpw(password.encode('utf8'), stored_hash):
        return False, generate_return_json(message=f"Wrong password for user {username}", status=302)
    return True, None


class Register(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower()),
                                                      posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        # check_credentials is called without password, only to confirm new user doesn't already exist
        user_exists, ret_map = check_credentials(username)
        if user_exists:
            return ret_map
        password = posted_data[PASSWORD.lower()]
        hashed_password = bcrypt.hashpw(password.encode('utf8'), bcrypt.gensalt())

        users.insert_one({
            USERNAME: username,
            PASSWORD: hashed_password,
            OWN: 0,
            DEBT: 0,
        })

        return generate_return_json(message="You have successfully signed up for the API", status=200)


def user_cash(username: str) -> int:
    return users.find_one({USERNAME: username}, {OWN: 1})[OWN]


def user_debt(username: str) -> int:
    return users.find_one({USERNAME: username}, {DEBT: 1})[DEBT]


def update_balance(username: str, balance: int):
    users.update_one({USERNAME: username}, {"$set": {OWN: balance}})


def update_debt(username: str, balance: int):
    users.update_one({USERNAME: username}, {"$set": {DEBT: balance}})


def validate_amount(amount) -> tuple:
    if amount <= 0:
        ret_map = generate_return_json(message="The amount of money must be greater than 0", status=304)
        return False, ret_map
    return True, None


def validate_balance(username: str, amount: int) -> tuple:
    cash = user_cash(username)
    if cash < amount:
        ret_map = generate_return_json(message=f"Your account balance is below {amount}, please add or take a loan",
                                       status=304)
        return False, ret_map
    return True, None


def take_bank_fee(fee):
    bank_cash = user_cash(username=BANK)
    update_balance(username=BANK, balance=bank_cash + fee)


class Add(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower(), AMOUNT),
                                                      posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        password = posted_data[PASSWORD.lower()]
        credentials_are_ok, ret_map = check_credentials(username=username, password=password)
        if not credentials_are_ok:
            return ret_map

        amount = posted_data[AMOUNT]
        amount_is_ok, ret_map = validate_amount(amount=amount)
        if not amount_is_ok:  # valid amount (positive number)
            return ret_map

        cash = user_cash(username=username)
        update_balance(username=username, balance=cash+amount-FEE)
        take_bank_fee(fee=FEE)

        return generate_return_json(message="Amount successfully added to the account", status=200)


class Transfer(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower(),
                                                                           TO, AMOUNT), posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        password = posted_data[PASSWORD.lower()]
        credentials_are_ok, ret_map = check_credentials(username=username, password=password)
        if not credentials_are_ok:
            return ret_map

        transfer_to = posted_data[TO]
        user_exists, ret_map = check_credentials(transfer_to)
        if not user_exists:  # receiver user does not exist
            return ret_map

        amount = posted_data[AMOUNT]
        amount_is_ok, ret_map = validate_amount(amount=amount)
        if not amount_is_ok:  # valid transfer amount (positive number)
            return ret_map

        balance_is_ok, ret_map = validate_balance(username=username, amount=amount+FEE)
        if not balance_is_ok:  # deny transfer if balance is below transfer amount
            return ret_map

        cash_from = user_cash(username=username)
        update_balance(username=username, balance=cash_from-amount-FEE)  # take the fee rom source...
        cash_to = user_cash(username=transfer_to)
        update_balance(username=transfer_to, balance=cash_to+amount)  # ...not from receiver
        take_bank_fee(fee=FEE)

        return generate_return_json(message="Amount transferred successfully", status=200)


class Balance(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower()),
                                                      posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        password = posted_data[PASSWORD.lower()]
        credentials_are_ok, ret_map = check_credentials(username=username, password=password)
        if not credentials_are_ok:
            return ret_map

        user_balance = users.find_one({USERNAME: username}, {OWN: 1, DEBT: 1})

        return generate_return_json(message=f"Your balance is {user_balance[OWN]}, debt is {user_balance[DEBT]}",
                                    status=200)


class TakeLoan(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower(), AMOUNT),
                                                      posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        password = posted_data[PASSWORD.lower()]
        credentials_are_ok, ret_map = check_credentials(username=username, password=password)
        if not credentials_are_ok:
            return ret_map

        amount = posted_data[AMOUNT]
        amount_is_ok, ret_map = validate_amount(amount=amount)
        if not amount_is_ok:  # valid amount (positive number)
            return ret_map

        cash = user_cash(username=username)
        debt = user_debt(username=username)
        update_balance(username=username, balance=cash+amount)
        update_debt(username=username, balance=debt+amount+FEE)
        take_bank_fee(fee=FEE)

        return generate_return_json(message="Loan added to your account", status=200)


class PayLoan(Resource):
    def post(self):
        posted_data = request.get_json()

        parameters_are_ok, ret_map = check_parameters(required_parameters=(USERNAME.lower(), PASSWORD.lower(), AMOUNT),
                                                      posted_data=posted_data)
        if not parameters_are_ok:
            return ret_map

        username = posted_data[USERNAME.lower()]
        password = posted_data[PASSWORD.lower()]
        credentials_are_ok, ret_map = check_credentials(username=username, password=password)
        if not credentials_are_ok:
            return ret_map

        amount = posted_data[AMOUNT]
        amount_is_ok, ret_map = validate_amount(amount=amount)
        if not amount_is_ok:  # valid amount (positive number)
            return ret_map

        cash = user_cash(username=username)
        debt = user_debt(username=username)
        if amount > debt:
            amount = debt

        balance_is_ok, ret_map = validate_balance(username=username, amount=amount + FEE)
        if not balance_is_ok:  # deny payment if balance is below payment amount
            return ret_map

        update_balance(username=username, balance=cash-amount-FEE)
        update_debt(username=username, balance=debt-amount)
        take_bank_fee(fee=FEE)

        return generate_return_json(message="Successful loan payment", status=200)


api.add_resource(Register, '/register')
api.add_resource(Add, '/add')
api.add_resource(Transfer, '/transfer')
api.add_resource(Balance, '/balance')
api.add_resource(TakeLoan, '/take_loan')
api.add_resource(PayLoan, '/pay_loan')

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
