import numpy as np
import matplotlib.pyplot as plt
from sklearn.base import OutlierMixin
from sklearn.metrics import accuracy_score
from sklearn.neighbors._base import UnsupervisedMixin
from sklearn.utils import check_array

import neat
import visualize
from sklearn import datasets
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from anomalyDetection import AnomalyDetectionConfig, AnomalyDetection
import pandas as pd

"""
Constants:
    - MAX_ACCUARCY depends on chosen dataset, try to manually tweak it.
"""

MAX_ACCURACY = 92000


def eval_genomes(genomes, config, X):
    global current_best_accuracy
    for genome_id, genome in genomes:
        accuracy = MAX_ACCURACY
        encoder, decoder = neat.nn.FeedForwardNetwork.create_autoencoder(genome, config)
        for input in X:
            bottleneck_output = encoder.activate(input)
            reconstructed = decoder.activate(bottleneck_output)
            for expected, output in zip(input, reconstructed):
                accuracy -= (expected - output) ** 2

        genome.fitness = accuracy


class NeatOutlier(OutlierMixin, UnsupervisedMixin):
    def __init__(self, config, generations=100, sensitivity=None, debug=False, visualize=False,
                 ensemble=False):
        super().__init__()
        self.generations = generations
        self.debug = debug
        self.encoder = None
        self.decoder = None
        self.sensitivity = sensitivity
        self.thresholds = []
        self.visualize = visualize
        self.ensemble = ensemble
        self.config = config

    def fit_predict(self, X, y=None):
        return self.fit(X).predict(X)

    def fit(self, X, y=None):

        population = neat.Population(self.config)
        stats = neat.StatisticsReporter()

        population.add_reporter(stats)
        population.add_reporter(neat.StdOutReporter(True))

        winner = population.run(eval_genomes, X, self.generations)
        stats.save()

        self.encoder, self.decoder = neat.nn.FeedForwardNetwork.create_autoencoder(winner, self.config)

        """Useful only on small input dimensions"""
        # visualize.plot_slider(X, self.encoder, self.decoder, view=True)

        visualize.draw_net_encoder(config, winner.encoder, True,
                                   node_colors={key: 'yellow' for key in winner.encoder.nodes},
                                   show_disabled=True)

        visualize.draw_net_decoder(config, winner.decoder, True,
                                   node_colors={key: 'yellow' for key in winner.decoder.nodes},
                                   show_disabled=True)

        visualize.plot_stats(stats, ylog=False, view=True)
        visualize.plot_species(stats, view=True)

        res = []
        for i, x in enumerate(X):
            bottle_neck = self.encoder.activate(x)
            output = self.decoder.activate(bottle_neck)
            res.append((i, sum(abs(output - x))))

        res.sort(reverse=False, key=lambda x: x[1])
        if self.sensitivity is not None:
            m1 = int(round(len(res) * self.sensitivity))
            m0 = m1 - 1
            self.thresholds.append((res[m1][1] + res[m0][1]) / 2)
        else:
            i_max_diff = np.argmax(np.diff([i2 for _, i2 in res]))
            m0 = i_max_diff
            self.thresholds.append((res[m0 + 1][1] + res[m0][1]) / 2)

        return self

    def predict(self, X):
        """Predict the labels (1 inlier, 0 outlier) of X according to LOF.

        This method allows to generalize prediction to *new observations* (not
        in the training set). Only available for novelty detection (when
        novelty is set to True).

        Parameters
        ----------
        X : array-like, shape (n_samples, n_features)
            The query sample or samples to compute the Local Outlier Factor
            w.r.t. to the training samples.

        Returns
        -------
        is_inlier : array, shape (n_samples,)
            Returns 0 for anomalies/outliers and +1 for inliers.
        """
        if (X is None) or (len(self.thresholds) < 1):
            return None

        X = check_array(X, accept_sparse='csr')
        is_inlier = np.ones(X.shape[0], dtype=int)
        for i, x in enumerate(X):
            outputs = []
            for j in range(len(self.thresholds)):
                bottle_neck = self.encoder.activate(x)
                output = self.decoder.activate(bottle_neck)
                if sum(abs(output - x)) > self.thresholds[j]:
                    outputs.append(0)
                else:
                    outputs.append(1)

                is_inlier[i] = max(set(outputs), key=outputs.count)  # Mode of all, majority voting

        return is_inlier


if __name__ == '__main__':
    print("Program start...")

    """Prepare dataset for anomaly detection based on configuration file"""
    config = AnomalyDetectionConfig(neat.AutoencoderGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                                    neat.DefaultStagnation, 'evolve-autoencoder.cfg')

    """Select the dataset"""
    with open("../../datasets/fault_detection.csv") as f:
        dataset = pd.read_csv(f, delimiter=";").to_numpy()
        data = dataset[:, 0:59]
        target = dataset[:, -1]

    """
        Since we are interested to perform unsupervised* anomaly detection, we will help
        the algorithm by reducing the amount of anomalous data instances. By doing this
        algorithm learn better to encode/decode majority of data (normal instances).
        As a result minority of data (anomalies) will be reconstructed worst and therefore,
        they will be more likely to be mark as a true positives anomalies. 
        
        *Disclaimer: One could argue that this is in fact a semi-supervised anomaly detection technique...
    """

    print(f"Anomaly label is for class: {config.anomaly_label}")

    """Link is explaining the bellow step"""
    # https://towardsdatascience.com/what-and-why-behind-fit-transform-vs-transform-in-scikit-learn-78f915cf96fe
    data = StandardScaler().fit_transform(data)

    X_train, X_test, y_train, y_test = train_test_split(data, target, test_size=0.85, random_state=42)

    """If supervised anomaly detection is intended, then we can remove anomalies from training"""
    # X_train = X_train[y_train != config.anomaly_label, :]

    """Turning multiple class data labels to binary"""
    y_test = [0 if str(yi) == config.anomaly_label else 1 for yi in y_test]

    anomaly_detection = AnomalyDetection(X_test, y_test, [1], [0])

    """Adjust number of generations"""
    neat_outlier = NeatOutlier(config, debug=True, generations=100, visualize=True, ensemble=True,
                               sensitivity=0.8)

    """Perform neuroevolution on training dataset"""
    neat_outlier.fit(X_train)

    predictions = neat_outlier.predict(X_test)
    acc = accuracy_score(predictions, y_test)
    print(f"Accuracy of winner model is: {acc}")

    """Ploting results from anomaly detection on graph"""
    anomaly_detection.find(neat_outlier.encoder, neat_outlier.decoder)
    visualize.plot_metrics(anomaly_detection.metrics, True)

    print("Program end...")
