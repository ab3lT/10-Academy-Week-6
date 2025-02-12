import pandas as pd
from flask import Flask, request, render_template, jsonify
from flasgger import Swagger, swag_from
from load_model import load_model
import sys, os

# Add the parent directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from scripts.feature_engineering import FeatureEngineering  # Adjusted import statement
from scripts.credit_risk_eda import CreditRiskEDA

# Initialize Flask app
app = Flask(__name__)
swagger = Swagger(app)  # Initialize Swagger

# Load the model once at the start
model = load_model('../model/best_model.pkl')

@app.route('/', methods=['GET'])
def index():
    """Render the main index page."""
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
@swag_from({
    'tags': ['Prediction'],
    'description': 'Handle prediction requests from the web interface.',
    'parameters': [
        {
            'name': 'TransactionId',
            'in': 'formData',
            'type': 'integer',
            'required': True,
            'description': 'Transaction ID'
        },
        {
            'name': 'CustomerId',
            'in': 'formData',
            'type': 'integer',
            'required': True,
            'description': 'Customer ID'
        },
        {
            'name': 'ProductCategory',
            'in': 'formData',
            'type': 'string',
            'required': True,
            'description': 'Product category of the transaction'
        },
        {
            'name': 'ChannelId',
            'in': 'formData',
            'type': 'string',
            'required': True,
            'description': 'Channel ID for the transaction'
        },
        {
            'name': 'Amount',
            'in': 'formData',
            'type': 'number',
            'required': True,
            'description': 'Transaction amount'
        },
        {
            'name': 'TransactionStartTime',
            'in': 'formData',
            'type': 'string',
            'required': True,
            'description': 'Start time of the transaction (ISO format)'
        },
        {
            'name': 'PricingStrategy',
            'in': 'formData',
            'type': 'integer',
            'required': True,
            'description': 'Pricing strategy for the transaction'
        }
    ],
    'responses': {
        200: {
            'description': 'Prediction successful',
            'examples': {
                'application/json': {
                    'customer_id': 123,
                    'predicted_risk': 'Good'
                }
            }
        },
        400: {
            'description': 'Invalid input',
            'examples': {
                'application/json': {
                    'error': 'Invalid input: ...'
                }
            }
        }
    }
})
def predict():
    """Handle prediction requests from the web interface."""
    return handle_prediction()

@app.route('/api/predict', methods=['POST'])
@swag_from({
    'tags': ['Prediction'],
    'description': 'Handle prediction requests from the API.',
    'parameters': [
        {
            'name': 'body',
            'in': 'body',
            'required': True,
            'schema': {
                'type': 'object',
                'properties': {
                    'TransactionId': {'type': 'integer'},
                    'CustomerId': {'type': 'integer'},
                    'ProductCategory': {'type': 'string'},
                    'ChannelId': {'type': 'string'},
                    'Amount': {'type': 'number'},
                    'TransactionStartTime': {'type': 'string', 'format': 'date-time'},
                    'PricingStrategy': {'type': 'integer'}
                },
                'required': [
                    'TransactionId', 'CustomerId', 'ProductCategory',
                    'ChannelId', 'Amount', 'TransactionStartTime', 'PricingStrategy'
                ]
            }
        }
    ],
    'responses': {
        200: {
            'description': 'Prediction successful',
            'examples': {
                'application/json': {
                    'customer_id': 123,
                    'predicted_risk': 'Good'
                }
            }
        },
        400: {
            'description': 'Invalid input',
            'examples': {
                'application/json': {
                    'error': 'Invalid input: ...'
                }
            }
        }
    }
})
def api_predict():
    """Handle prediction requests from the API."""
    return handle_prediction()

def handle_prediction():
    """Shared logic for handling prediction requests."""
    try:
        input_data = {
            'TransactionId': int(request.form['TransactionId']) if request.method == 'POST' and 'TransactionId' in request.form else int(request.json['TransactionId']),
            'CustomerId': int(request.form['CustomerId']) if request.method == 'POST' and 'CustomerId' in request.form else int(request.json['CustomerId']),
            # 'ProductId': int(request.form['ProductId']) if request.method == 'POST' and 'ProductId' in request.form else int(request.json['ProductId']),
            'ProductCategory': request.form['ProductCategory'] if request.method == 'POST' and 'ProductCategory' in request.form else request.json['ProductCategory'],
            'ChannelId': request.form['ChannelId'] if request.method == 'POST' and 'ChannelId' in request.form else request.json['ChannelId'],
            'Amount': float(request.form['Amount']) if request.method == 'POST' and 'Amount' in request.form else float(request.json['Amount']),
            'TransactionStartTime': pd.to_datetime(request.form['TransactionStartTime'], utc=True),
            'PricingStrategy': int(request.form['PricingStrategy']) if request.method == 'POST' and 'PricingStrategy' in request.form else int(request.json['PricingStrategy'])
        }

        # Prepare input data as DataFrame
        input_df = pd.DataFrame([input_data])

        # Feature Engineering
        fe = FeatureEngineering()
        input_df = fe.create_aggregate_features(input_df)
        input_df = fe.create_transaction_features(input_df)
        input_df = fe.extract_time_features(input_df)

        # Encode categorical features
        categorical_cols = ['ProductCategory', 'ChannelId']
        input_df = fe.encode_categorical_features(input_df, categorical_cols)

        # Handle missing values and normalize features
        numeric_cols = input_df.select_dtypes(include='number').columns.tolist()
        exclude_cols = ['Amount', 'TransactionId']
        numeric_cols = [col for col in numeric_cols if col not in exclude_cols]

        input_df = fe.normalize_numerical_features(input_df, numeric_cols, method='standardize')

        # RFM Calculation
        rfm = CreditScoreRFM(input_df.reset_index())
        rfm_df = rfm.calculate_rfm()
        final_df = pd.merge(input_df, rfm_df, on='CustomerId', how='left')

        # Define all final features expected in the output
        final_features = [
            'PricingStrategy', 'Transaction_Count', 'Debit_Count', 'Credit_Count',
            'Debit_Credit_Ratio', 'Transaction_Month', 'Transaction_Year',
            'ProductCategory_financial_services', 'ChannelId_ChannelId_2',
            'ChannelId_ChannelId_3', 'Recency', 'Frequency'
        ]

        # Ensure all final features exist in the DataFrame and fill missing ones with 0
        final_df = final_df.reindex(columns=final_features, fill_value=0)
        
        # Make prediction
        prediction = model.predict(final_df)
        predicted_risk = 'Good' if prediction[0] == 0 else 'Bad'
        print(predicted_risk)
        return jsonify({
            'customer_id': input_data['CustomerId'],
            'predicted_risk': predicted_risk
        })

    except ValueError as ve:
        print("ValueError:", str(ve))
        return jsonify({'error': 'Invalid input: ' + str(ve)}), 400
    except KeyError as ke:
        print("KeyError:", str(ke))
        return jsonify({'error': 'Missing input data: ' + str(ke)}), 400
    except Exception as e:
        print("General Exception:", str(e))
        return jsonify({'error': 'An error occurred: ' + str(e)}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
