# -*- coding: utf-8 -*-

# External imports
import numpy
import pandas

# Internal imports (if any)


def pricing(df, columns, coeffs=None, debug=False, price_column=None):
    """
    Price cards present at df, computing the coeffs for the given columns.

    :param :class `pandas.DataFrame`: df: data frame containing the cards to price.
    :param list columns: columns to compute coeffs for.
    :param coeffs: precomputed set of coeffs for the selected columns.
    :param bool debug: print the computed coeffs
    :param str price_column: name of the column to place the 'price'.
    :return: a matrix with the computed coeffs (if coeffs is provided, return the same coeffs).
    """
    df[u'intrinsic'] = -1
    a = df.as_matrix(columns)
    if coeffs is None:
        b = df.as_matrix([u'cost'])
        coeffs = numpy.linalg.lstsq(a, b)[0]
        if debug:
            print(pandas.DataFrame(coeffs.T, columns=columns))
    df[price_column or u'price'] = numpy.dot(a, coeffs).T[0]
    return coeffs

