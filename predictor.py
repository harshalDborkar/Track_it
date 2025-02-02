import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import logging


class PricePredictionModel:
    def __init__(self, dataset):
        self.dataset = dataset
        self.model = None
        self.scaler = None

    def preprocess_data(self):
        """Preprocess data: clean prices and create features."""
        try:
            # Clean prices in all columns except the first two (name, link)
            price_columns = [col for col in self.dataset.columns if col.startswith("2024-")]
            
            def clean_price(price):
                if isinstance(price, str):
                    price = price.replace('₹', '').replace(',', '').strip()
                try:
                    return float(price) if float(price) > 0 else None
                except ValueError:
                    return None
            
            self.dataset[price_columns] = self.dataset[price_columns].map(clean_price)

            # Drop rows with insufficient price data
            self.dataset.dropna(subset=price_columns, thresh=2, inplace=True)

            # Calculate price trends
            self.dataset['avg_price'] = self.dataset[price_columns].mean(axis=1)
            self.dataset['price_std'] = self.dataset[price_columns].std(axis=1)
            self.dataset['price_change'] = self.dataset[price_columns].apply(
                lambda row: (row.max() - row.min()) / row.max() if row.max() else 0, axis=1
            )
            
            # Calculate price drop probability
            self.dataset['price_drop_prob'] = np.where(
                self.dataset['price_change'] > 0.05,  # More than 5% price change
                self.dataset['price_change'] * 100,   # Convert to percentage
                0  # No significant price change
            )
            
            # Drop rows with invalid trends
            self.dataset.dropna(subset=['price_std', 'price_change'], inplace=True)

            logging.info("Data preprocessing completed successfully.")
            return self.dataset
        except Exception as e:
            logging.error(f"Error during data preprocessing: {e}")
            raise

    def train_model(self, target_column="price_drop_prob"):
        """Train a model to predict price drop probability."""
        try:
            # Features and target
            X = self.dataset[['price_std', 'price_change']]
            y = self.dataset[target_column]

            # Split data
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

            # Scale features
            self.scaler = StandardScaler()
            X_train = self.scaler.fit_transform(X_train)
            X_test = self.scaler.transform(X_test)

            # Train classification model (RandomForest can handle regression and classification)
            self.model = RandomForestRegressor(random_state=42)
            self.model.fit(X_train, y_train)
            score = self.model.score(X_test, y_test)

            logging.info(f"Model trained successfully with R^2 score: {score}")
        except Exception as e:
            logging.error(f"Error during model training: {e}")
            raise

    def predict(self, input_data):
        """Predict price drop probability based on input features."""
        try:
            # Ensure input is a valid list or numpy array
            input_features = np.array(input_data).reshape(1, -1)
            
            # Transform input features
            input_scaled = self.scaler.transform(input_features)
            
            # Predict probability of price drop
            prediction = self.model.predict(input_scaled)[0]
            
            # Clip prediction between 0 and 100
            prediction = max(0, min(int(prediction), 100))
            
            return prediction
        except Exception as e:
            logging.error(f"Error during prediction: {e}")
            return None