import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


class AcidBase:
    def __init__(self,
                 analyte_is_acidic,
                 pka_values,
                 pkt_values,
                 strong_analyte=True,
                 strong_titrant=True,
                 precision=0.01,
                 kw=1.023 * (10 ** -14),
                 ):
        self.analyte_is_acidic = analyte_is_acidic
        self.k_analyte = self.pk_to_k(pka_values)
        self.k_titrant = self.pk_to_k(pkt_values)
        self.titrant_acidity = not analyte_is_acidic
        self.strong_analyte = strong_analyte
        self.strong_titrant = strong_titrant
        self.precision = precision
        self.kw = kw
        self.ph, self.hydronium, self.hydroxide = self.starting_phs()

    @staticmethod
    def pk_to_k(pk):
        """
        Converts a pk, or an array or pk's to a k or an array of k's

        :param pk:
            A or a list of pK values for a compound.
        :return:
            An array of the pk values respective k values in order.

        """

        return np.array(10. ** (- np.array(pk)))

    def starting_phs(self, min_ph=0, max_ph=14):
        """
        Creates a starting range of pH, hydronium, and hydroxide values.
        :param min_ph:
            The minimum value of pH to calculate from.
        :param max_ph:
            The maximum value of pH to calculate from.
        :return: ph, h, oh
            pH, hydronium concentration, and hydroxide concentration.
        """

        ph = np.array(np.arange(min_ph, max_ph + self.precision, step=self.precision))
        h = 10 ** (-ph.copy())
        oh = self.kw / h
        return ph, h, oh


class Bjerrum(AcidBase):

    def __init__(self,
                 analyte_is_acidic,
                 pka_values,
                 pkt_values,
                 strong_analyte=True,
                 strong_titrant=True,
                 precision=0.01,
                 kw=1.023 * (10 ** -14)):

        super().__init__(analyte_is_acidic, pka_values, pkt_values, strong_analyte, strong_titrant, precision, kw)

        self.alpha_analyte = self.alpha_values(k=self.k_analyte, acid=self.analyte_is_acidic)
        self.alpha_titrant = self.alpha_values(k=self.k_titrant, acid=self.titrant_acidity)

    @staticmethod
    def scale_alphas(arr):

        new_arr = []
        for item in arr:
            sub_arr = []
            for i, sub_item in enumerate(item):
                sub_item *= i
                sub_arr.append(sub_item)
            new_arr.append(sub_arr)
        new_arr = np.array(new_arr)

        return new_arr

    def alpha_values(self, k, acid=True):

        # Convert the k values to a list to help with matrix transformations.
        k = np.array(k)

        # If the k values are for K_b, convert to K_a. --> K_1 = K_w / K_n , K_2 = K_w / K_(n-1)
        if not acid:
            k = self.kw / np.flip(k)

        # The functionality of an acid or base can be determined by the number of dissociation constants it has.
        n = len(k)

        # Get the values for the [H+]^n power
        powers = np.array([x for x in range(n, -1, -1)])  # List of powers
        h_vals = np.array([np.array(self.hydronium ** i) for i in powers])  # List of H values raised to the powers

        # Get the products of the k values.
        k_vals = [np.prod(k[0:x]) for x in range(n + 1)]

        # Prod and Sum the h and k values
        h_vals = h_vals.T  # Reorient the array for multiplication
        denoms_arr = np.multiply(h_vals, k_vals)  # Product of the sub-elements of the denominator
        denoms = np.sum(denoms_arr, axis=1)  # Sum of the sub-elements of the denominator

        # Do the outermost alpha value calculation
        tda = np.transpose(denoms_arr)  # Transpose the array to the correct orientation for the division
        div_arr = np.divide(tda, denoms)  # Divide
        alphas = np.transpose(div_arr)  # Re-transpose to the logically correct orientation

        if not acid:
            return np.flip(alphas, axis=0)

        return np.array(alphas)

    def plot_alpha_curve(self, title="Alpha Value Plot"):

        plt.plot(self.ph, self.alpha_analyte)
        plt.title(title)
        plt.show()

    def write_alpha_data(self, title="Alpha Value Data", file_headers=False, species_names=None):

        # Initialize the dataframe with the ph values
        data_dict = {"pH": self.ph}

        # Add the alpha values for each analyte species
        if species_names is None:  # If names are not specified, just use generics.
            for num, alpha in enumerate(self.alpha_analyte.T):
                data_dict[f"alpha{num}"] = alpha
        else:  # If names are specified, use them.
            for num, alpha in enumerate(self.alpha_analyte.T):
                try:
                    data_dict[species_names[num]] = alpha
                except IndexError:
                    raise ValueError("You have not supplied enough species names!")

        # Make and write the data frame to a csv
        data = pd.DataFrame(data_dict)
        data.to_csv(f"{title}.csv", index=False, header=file_headers)


class Titration(Bjerrum):
    """
    A class which defines a titration and predominance curve based on the used analyte and titrant.
    """

    def __init__(self,
                 analyte_is_acidic,
                 volume_analyte,
                 concentration_analyte,
                 concentration_titrant,
                 pka_values,
                 pkt_values,
                 strong_analyte=True,
                 strong_titrant=True,
                 precision=0.01,
                 kw=1.023 * (10 ** -14),
                 ):
        super().__init__(analyte_is_acidic, pka_values, pkt_values, strong_analyte, strong_titrant, precision, kw)

        # Analyte information
        self.concentration_analyte = concentration_analyte
        self.volume_analyte = volume_analyte
        self.pka_values = pka_values

        # Titrant Information
        self.concentration_titrant = concentration_titrant
        self.pkt_values = pkt_values

        # Calculate the respective titrant values for each pH
        self.volume_titrant, self.phi = self.volume_calculator(self.titrant_acidity)

    def check_values(self):

        # Go until you are 1 past the last sub-reaction.
        limiter = len(self.pka_values) + 1

        good_val_index = np.where((self.phi >= 0) & (self.phi <= limiter))

        # Cut the bad data out of each dataset.
        volume_titrant = self.volume_titrant[good_val_index]
        ph = self.ph[good_val_index]

        return volume_titrant, ph

    def volume_calculator(self, acid_titrant):

        # Alpha values scaled by their index
        scaled_alphas_analyte = self.scale_alphas(self.alpha_analyte)
        scaled_alphas_titrant = self.scale_alphas(self.alpha_titrant)

        # Sum the scaled alpha values. Axis=1 forces the summation to occur for each individual [H+] value.
        # Since strong acids/bases fully dissociate, they only appear in their pure form, thus, their alpha values = 1
        if self.strong_analyte:
            summed_scaled_alphas_analyte = np.array([1])
        else:
            summed_scaled_alphas_analyte = np.sum(scaled_alphas_analyte, axis=1)

        if self.strong_titrant:
            summed_scaled_alphas_titrant = np.array([1])
        else:
            summed_scaled_alphas_titrant = np.sum(scaled_alphas_titrant, axis=1)

        beta = self.hydronium - self.hydroxide  # No technical definition

        # Conditional addition or subtraction based on the titrant.
        if acid_titrant:
            numerator = summed_scaled_alphas_analyte + (beta / self.concentration_analyte)
            denominator = summed_scaled_alphas_titrant - (beta / self.concentration_titrant)
        else:
            numerator = summed_scaled_alphas_analyte - (beta / self.concentration_analyte)
            denominator = summed_scaled_alphas_titrant + (beta / self.concentration_titrant)

        # Solve for the volume
        phi = numerator / denominator
        volume = phi * self.volume_analyte * self.concentration_analyte / self.concentration_titrant
        return volume, phi

    def plot_titration_curve(self, title="Titration Curve"):

        # Remove values from indices where the volume is negative or extremely large.
        volume, pH = self.check_values()

        plt.plot(volume, pH)
        plt.title(title)
        plt.show()

    def write_titration_data(self, title="Titration Curve Data", file_headers=False):
        # Make dataframe.
        volume, pH = self.check_values()
        data = pd.DataFrame({"volume": volume,
                             "pH": pH})

        # Write to a csv.
        data.to_csv(f"{title}.csv", index=False, header=file_headers)
