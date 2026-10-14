"""Log the fraud-detection training run (produced by the official tutorial's
1_experiment_train.ipynb) to MLflow: parameters, evaluation metrics, and the
ONNX model artifact. This is additive instrumentation on top of the
unmodified tutorial notebook, not a change to the tutorial's model/data/training code.
"""
import pickle

import mlflow
import numpy as np
import onnxruntime as rt
from sklearn.metrics import precision_score, recall_score

mlflow.set_experiment("fraud-detection")

with open("artifact/scaler.pkl", "rb") as handle:
    scaler = pickle.load(handle)
with open("artifact/test_data.pkl", "rb") as handle:
    X_test, y_test = pickle.load(handle)

model_path = "models/fraud/1/model.onnx"
sess = rt.InferenceSession(model_path, providers=rt.get_available_providers())
input_name = sess.get_inputs()[0].name
output_name = sess.get_outputs()[0].name

y_pred_temp = sess.run([output_name], {input_name: X_test.astype(np.float32)})
y_pred_temp = np.asarray(np.squeeze(y_pred_temp[0]))
threshold = 0.95
y_pred = np.where(y_pred_temp > threshold, 1, 0)

y_test_arr = y_test.squeeze()
correct = np.equal(y_pred, y_test_arr).sum().item()
accuracy = (correct / len(y_pred)) * 100
precision = precision_score(y_test_arr, np.round(y_pred))
recall = recall_score(y_test_arr, np.round(y_pred))

with mlflow.start_run(run_name="fraud-detection-tutorial-run"):
    mlflow.log_param("model_type", "keras_sequential_nn")
    mlflow.log_param("epochs", 2)
    mlflow.log_param("features", "distance_from_last_transaction,ratio_to_median_purchase_price,used_chip,used_pin_number,online_order")
    mlflow.log_param("threshold", threshold)
    mlflow.log_metric("accuracy_pct", accuracy)
    mlflow.log_metric("precision", precision)
    mlflow.log_metric("recall", recall)
    mlflow.log_artifact(model_path)
    print(f"Logged run: accuracy={accuracy:.1f}%, precision={precision:.4f}, recall={recall:.4f}")
