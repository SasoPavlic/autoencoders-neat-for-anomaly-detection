from configparser import ConfigParser

import numpy as np
from matplotlib import pyplot as plt
from sklearn.metrics import auc
from sklearn.metrics import roc_curve, mean_squared_error
import seaborn as sns

from neat.config import Config


class AnomalyDetectionConfig(Config):
    def __init__(self, AutoencoderGenome, DefaultReproduction, DefaultSpeciesSet, DefaultStagnation, filename):
        super().__init__(AutoencoderGenome, DefaultReproduction, DefaultSpeciesSet, DefaultStagnation, filename)

        config = ConfigParser()
        self.path = filename
        config.read(self.path)
        self.generations = int(config.get('NEAT', 'generations'))
        self.anomaly_label = str(config.get('AnomalyDetection', 'anomaly_label'))
        self.curriculum_levels = str(config.get('AnomalyDetection', 'curriculum_levels'))
        self.data_percentage = float(config.get('AnomalyDetection', 'data_percentage'))
        self.test_size = float(config.get('AnomalyDetection', 'test_size'))

# TODO Rename class to CurriculumAnomalyDetection
class AnomalyDetection(object):

    def __init__(self, X_train, X_test, y_train, y_test, valid_label, anomaly_label, all_generations,
                 curriculum_levels):
        # TODO make it more efficient
        # Convert pandas dataframe to numpy array [:-1] to remove label column Level
        # self.train_X_array = X_train  # .to_numpy()
        # self.train_Y_array = y_train  # .to_numpy()

        if curriculum_levels == 'three':
            # Filter dataframe by column value
            self.df_easy_three = X_train[X_train['Level'] == 'Easy']
            self.df_medium_three = X_train[X_train['Level'] == 'Medium']
            self.df_hard_three = X_train[X_train['Level'] == 'Hard']

        elif curriculum_levels == 'two':
            self.df_easy_two = X_train[X_train['Level'] == 'Easy']
            self.df_hard_two = X_train[X_train['Level'] == 'Hard']

        else:
            self.df_zero = X_train

        self.test_X_array = X_test.to_numpy()
        self.test_Y_array = y_test



        self.valid_label = valid_label
        self.anomaly_label = anomaly_label
        self.all_generations = all_generations
        self.curriculum_levels = curriculum_levels
        self.acc_list = []

        self.metrics = []
        self.FPR_array = None
        self.TPR_array = None
        self.roc_auc = None
        self.AUC = None
        self.MSE = None
        self.test_counter = 0

    def calculate_auc(self, targets, scores):
        try:
            FPR_array = dict()
            TPR_array = dict()
            thresholds = dict()
            roc_auc = dict()
            for i in range(2):
                FPR_array[i], TPR_array[i], thresholds[i] = roc_curve(targets, scores)
                roc_auc[i] = auc(FPR_array[i], TPR_array[i])

            AUC = round(roc_auc[0], 5)

        except Exception as e:
            print(e)
            AUC = 0.0

        return int(AUC * 10000)

    def calculate_fitness(self, encoder, decoder, generation):
        """Calculate mean squared error between original and reconstructed data
        """
        decoded_instances = []
        scores = []
        targets = []
        df = None

        # TODO make generation percentage parametric
        gen_percentage = generation / self.all_generations * 100

        if self.curriculum_levels == 'three':

            if gen_percentage <= 40:
                df = self.df_easy_three

            elif 40 < gen_percentage <= 65:
                df = self.df_medium_three

            elif gen_percentage > 65:
                df = self.df_hard_three

        elif self.curriculum_levels == 'two':

            if gen_percentage <= 50:
                df = self.df_easy_two
            elif gen_percentage > 50:
                df = self.df_hard_two

        elif self.curriculum_levels == 'zero':
            df = self.df_zero

        for x, y in zip(df.to_numpy(), df['Heart_Disease']):
            data = x[2:-1]
            bottle_neck = encoder.activate(data)
            decoded = decoder.activate(bottle_neck)

            decoded_instances.append(decoded)
            targets.append(y)
            mse = mean_squared_error(data, decoded)
            # rmse = math.sqrt(mean_squared_error(data, decoded))
            scores.append(mse)

        auc_score = self.calculate_auc(targets, scores)
        median_mse = int(np.median(scores))
        fitness_score = auc_score - median_mse

        return fitness_score

    def calculate_final_mse(self, encoder, decoder):
        decoded_instances = []
        scores = []
        targets = []
        data = None
        for x, y in zip(self.test_X_array, self.test_Y_array):
            data = x[2:-1]

            bottle_neck = encoder.activate(data)
            decoded = decoder.activate(bottle_neck)

            decoded_instances.append(decoded)
            targets.append(y)
            mse = mean_squared_error(data, decoded)
            # rmse = math.sqrt(mean_squared_error(data, decoded))
            scores.append(round(mse, 2))

        # Return mse_list mean value
        return decoded_instances, scores, targets

    def calculate_roc_auc_curve(self, encoder, decoder):
        # https://stackoverflow.com/questions/58894137/roc-auc-score-for-autoencoder-and-isolationforest

        decoded_instances, scores, targets = self.calculate_final_mse(encoder, decoder)

        try:
            self.FPR_array = dict()
            self.TPR_array = dict()
            thresholds = dict()
            self.roc_auc = dict()
            for i in range(2):
                self.FPR_array[i], self.TPR_array[i], thresholds[i] = roc_curve(targets, scores)
                self.roc_auc[i] = auc(self.FPR_array[i], self.TPR_array[i])

            self.AUC = round(self.roc_auc[0], 5)

        except Exception as e:
            print(e)
            self.AUC = 0.0

        auc_score = int(self.AUC * 10000)
        self.MSE = int(np.median(scores))
        fitness_score = auc_score - self.MSE
        return fitness_score, scores
