""" This module contains procedures for applying astrometry and field corrections to meteor data.
"""

# The MIT License

# Copyright (c) 2016 Denis Vida

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


import sys
import math
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt

from MeteorTriangulation import date2JD, triangulate
from ParseCMNformat import parseInf, parsePlatepar



def applyFieldCorrection(x_poly, y_poly, X_res, Y_res, F_scale, X_data, Y_data, level_data):
    """ Apply field correction and vignetting correction to all given image points. 

    @param x_poly: [ndarray] 1D numpy array of 12 elements containing X axis polynomial parameters
    @param y_poly: [ndarray] 1D numpy array of 12 elements containing Y axis polynomial parameters
    @param X_res: [int] camera X axis resolution (longer)
    @param Y_res: [int] camera Y axis resolution (shorter)
    @param F_scale: [float] sum of image scales per each image axis (arcsec per px)
    @param X_data: [ndarray] 1D float numpy array containing X component of the detection point
    @param Y_data: [ndarray] 1D float numpy array containing Y component of the detection point
    @param level_data: [ndarray] 1D int numpy array containing levels of detection points

    @return (X_corrected, Y_corrected, levels_corrected): [tuple of ndarrays]
        X_corrected: 1D numpy array containing distortion corrected X component
        Y_corrected: 1D numpy array containing distortion corrected Y component
        level_data: 1D numpy array containing vignetting corrected levels
    """

    # Scale the resolution to CIF
    X_scale = X_res/384.0
    Y_scale = Y_res/288.0

    # Initialize final values containers
    X_corrected = np.zeros_like(X_data)
    Y_corrected = np.zeros_like(Y_data)
    levels_corrected = np.zeros_like(level_data, dtype=np.float64)

    i = 0

    data_matrix = np.vstack((X_data, Y_data, level_data)).T

    # Go through all given data points
    for Xdet, Ydet, level in data_matrix:

        # Scale the point coordinates to CIF resolution
        Xdet = (Xdet - X_res/2)/X_scale
        Ydet = (Ydet - Y_res/2)/Y_scale

        # Apply vignetting correction
        if (np.sqrt((Xdet - 192)**2 + (Ydet - 192)**2) > 120):
            level = level * (1 + 0.00245*(np.sqrt((Xdet - 192)**2 + (Ydet - 192)**2) - 120))

        X_pix = (
            Xdet 
            + x_poly[0]
            + x_poly[1] * Xdet
            + x_poly[2] * Ydet
            + x_poly[3] * Xdet**2
            + x_poly[4] * Xdet * Ydet
            + x_poly[5] * Ydet**2
            + x_poly[6] * Xdet**3
            + x_poly[7] * Xdet**2 * Ydet
            + x_poly[8] * Xdet * Ydet**2
            + x_poly[9] * Ydet**3
            + x_poly[10] * Xdet * np.sqrt(Xdet**2 + Ydet**2)
            + x_poly[11] * Ydet * np.sqrt(Xdet**2 + Ydet**2))

        Y_pix = (
            Ydet
            + y_poly[0]
            + y_poly[1] * Xdet
            + y_poly[2] * Ydet
            + y_poly[3] * Xdet**2
            + y_poly[4] * Xdet * Ydet
            + y_poly[5] * Ydet**2
            + y_poly[6] * Xdet**3
            + y_poly[7] * Xdet**2 * Ydet
            + y_poly[8] * Xdet * Ydet**2
            + y_poly[9] * Ydet**3
            + y_poly[10] * Ydet * np.sqrt(Xdet**2 + Ydet**2)
            + y_poly[11] * Xdet * np.sqrt(Xdet**2 + Ydet**2))


        # Scale back image coordinates
        X_pix = X_pix/F_scale
        Y_pix = Y_pix/F_scale

        # Store values to final arrays
        X_corrected[i] = X_pix
        Y_corrected[i] = Y_pix
        levels_corrected[i] = level

        i += 1

    return X_corrected, Y_corrected, levels_corrected



def XY2altAz(lat, lon, RA_d, dec_d, Ho, rot_param, X_data, Y_data):
    """ Convert image coordinates (X, Y) to sky altitude and azimuth. 

    @param lat: [float] latitude of the observer in degrees
    @param lon: [float] longitde of the observer in degress
    @param RA_d: [float] right ascension of the image centre (degrees)
    @param dec_d: [float] declination of the image centre (degrees)
    @param Ho: [float] referent hour angle
    @param rot_param: [float] field rotation parameter (degrees)
    @param X_data: [ndarray] 1D numpy array containing distortion corrected X component
    @param Y_data: [ndarray] 1D numpy array containing distortion corrected Y component

    @return (azimuth_data, altitude_data): [tuple of ndarrays]
        azimuth_data: [ndarray] 1D numpy array containing the azimuth of each data point (degrees)
        altitude_data: [ndarray] 1D numyp array containing the altitude of each data point (degrees)
    """

    # Initialize final values containers
    az_data = np.zeros_like(X_data)
    alt_data = np.zeros_like(X_data)

    # Convert declination to radians
    dec_rad = math.radians(dec_d)

    # Precalculate some parameters
    sl = math.sin(math.radians(lon))
    cl = math.cos(math.radians(lon))

    i = 0
    data_matrix = np.vstack((X_data, Y_data)).T

    # Go through all given data points
    for X_pix, Y_pix in data_matrix:

        # Caulucate the needed parameters
        radius = math.radians(np.sqrt(X_pix**2 + Y_pix**2))
        theta = math.radians((90 - rot_param + math.degrees(math.atan2(Y_pix, X_pix))) % 360)

        sin_t = math.sin(dec_rad)*math.cos(radius) + math.cos(dec_rad)*math.sin(radius)*math.cos(theta)
        Dec0det = math.atan2(sin_t, math.sqrt(1 - sin_t**2))

        sin_t = math.sin(theta)*math.sin(radius)/math.cos(Dec0det)
        cos_t = (math.cos(radius) - math.sin(Dec0det)*math.sin(dec_rad))/(math.cos(Dec0det)*math.cos(dec_rad))
        RA0det = RA_d - math.degrees(math.atan2(sin_t, cos_t)) % 360

        h = math.radians(Ho + lat - RA0det)
        sh = math.sin(h)
        sd = math.sin(Dec0det)
        ch = math.cos(h)
        cd = math.cos(Dec0det)

        x = -ch*cd*sl + sd*cl
        y = -sh*cd
        z = ch*cd*cl + sd*sl

        r = math.sqrt(x**2 + y**2)

        # Calculate azimuth and altitude
        azimuth = math.degrees(math.atan2(y, x)) % 360
        altitude = math.degrees(math.atan2(z, r))

        # Save calculated values to an output array
        az_data[i] = azimuth
        alt_data[i] = altitude
        
        i += 1

    return az_data, alt_data



def altAz2RADec(lat, lon, UT_corr, time_data, azimuth_data, altitude_data):
    """ Convert the azimuth and altitude in a given time and position on Earth to right ascension and 
        declination. 

    @param lat: [float] latitude of the observer in degrees
    @param lon: [float] longitde of the observer in degress
    @param UT_corr: [float] UT correction in hours (difference from local time to UT)
    @param time_data: [2D ndarray] numpy array containing time tuples of each data point (year, month, day, 
        hour, minute, second, millisecond)
    @param azimuth_data: [ndarray] 1D numpy array containing the azimuth of each data point (degrees)
    @param altitude_data: [ndarray] 1D numyp array containing the altitude of each data point (degrees)

    @return (JD_data, RA_data, dec_data): [tuple of ndarrays]
        JD_data: [ndarray] julian date of each data point
        RA_data: [ndarray] right ascension of each point
        dec_data: [ndarray] declination of each point
    """

    # Initialize final values containers
    JD_data = np.zeros_like(azimuth_data)
    RA_data = np.zeros_like(azimuth_data)
    dec_data = np.zeros_like(azimuth_data)

    # Precalculate some parameters
    sl = math.sin(math.radians(lon))
    cl = math.cos(math.radians(lon))

    i = 0
    data_matrix = np.vstack((azimuth_data, altitude_data)).T

    # Go through all given data points
    for azimuth, altitude in data_matrix:

        # Extract time
        Y, M, D, h, m, s, ms = time_data[i]

        # Convert altitude and azimuth to radians
        az_rad = math.radians(azimuth)
        alt_rad = math.radians(altitude)

        saz = math.sin(az_rad)
        salt = math.sin(alt_rad)
        caz = math.cos(az_rad)
        calt = math.cos(alt_rad)

        x = -saz*calt
        y = -caz*sl*calt + salt*cl
        HA = math.degrees(math.atan2(x,y))

        # Calculate the referent hour angle
        JD = date2JD(Y, M, D, h, m, s, ms, UT_corr=UT_corr)
        T=(JD - 2451545.0)/36525.0
        Ho = (280.46061837 + 360.98564736629*(JD - 2451545.0) + 0.000387933*T**2 - T**3/38710000.0) % 360

        RA = (Ho + lat - HA) % 360
        dec = math.degrees(math.asin(sl*salt + cl*calt*caz))

        # Save calculated values to an output array
        JD_data[i] = JD
        RA_data[i] = RA
        dec_data[i] = dec

        i += 1

    return JD_data, RA_data, dec_data



def calculateMagnitudes(level_data, ra_beg, ra_end, dec_beg, dec_end, duration, mag_0, mag_lev, 
    w_pix):
    """ Calculate the magnitude of the data points with given magnitude calibration parameters. 

    @param level_data: [ndarray] levels of the meteor centroid (arbirtary units)
    @param ra_beg: [float] right ascension of the meteor's beginning (degrees)
    @param ra_end: [float] right ascension of the meteor's end (degrees)
    @param dec_beg: [float] declination of the meteor's beginning (degrees)
    @param dec_end: [float] declination of the meteor's end (degrees)
    @param duration: [float] duration of the meteor in seconds
    @param mag_0: [float] magnitude calibration equation parameter (slope)
    @param mag_lev: [float] magnitude calibration equation parameter (intercept)
    @param w_pix: [float] minimum angular velocity of which to apply magnitude correction (arcsec/sec)

    @return magnitude_data: [ndarray] array of meteor's lightcurve apparent magnitudes
    """

    magnitude_data = np.zeros_like(level_data, dtype=np.float64)

    # Convert RA and Dec to radians
    ra_beg, ra_end, dec_beg, dec_end = map(np.radians, (ra_beg, ra_end, dec_beg, dec_end))

    # Calculate the length of the meteor trail
    length = np.degrees(np.arccos(np.sin(dec_beg)*np.sin(dec_end) + 
        np.cos(dec_beg)*np.cos(dec_end)*np.cos(ra_beg - ra_end)))

    # Calculate the angular velocty
    angular_v = length / float(duration)

    # Go through all levels of a meteor
    for i, level in enumerate(level_data):

        # Calculate the non-angular-velocity-corrected magnitude
        if np.log10(level) <= 3.2:
            magnitude = mag_0*np.log10(level) + mag_lev
        else:
            magnitude = -20*np.log10(level) + 64.5


        # Correct the magnitude for angular velocity
        if angular_v > w_pix:
            magnitude = magnitude -2.5*np.log10(angular_v/w_pix)

        # Save magnitude data to the output array
        magnitude_data[i] = magnitude


    return magnitude_data



def XY2CorrectedRADec(time_data, X_data, Y_data, level_data, UT_corr, lat, lon, Ho, X_res, Y_res, RA_d, dec_d, 
    rot_param, F_scale, w_pix, mag_0, mag_lev, x_poly, y_poly):
    """ A function that does the complete calibration and coordinate transformations of a meteor detection.

    First, it applies field distortion and vignetting correction on the data, then converts the XY coordinates
    to altitude and azimuth. Then it converts the altitude and azimuth data to right ascension and 
    declination. The resulting coordinates are in J2000.0 epoch.

    @param time_data: [2D ndarray] numpy array containing time tuples of each data point (year, month, day, 
        hour, minute, second, millisecond)
    @param X_data: [ndarray] 1D numpy array containing distortion corrected X component
    @param Y_data: [ndarray] 1D numpy array containing distortion corrected Y component
    @param level_data: [ndarray] levels of the meteor centroid (arbirtary units)
    @param UT_corr: [float] UT correction in hours (difference from local time to UT)
    @param lat: [float] latitude of the observer in degrees
    @param lon: [float] longitde of the observer in degress
    @param Ho: [float] referent hour angle
    @param X_res: [int] camera X axis resolution (longer)
    @param Y_res: [int] camera Y axis resolution (shorter)
    @param RA_d: [float] right ascension of the image centre (degrees)
    @param dec_d: [float] declination of the image centre (degrees)
    @param rot_param: [float] field rotation parameter (degrees)
    @param F_scale: [float] sum of image scales per each image axis (arcsec per px)
    @param w_pix: [float] minimum angular velocity of which to apply magnitude correction (arcsec/sec)
    @param mag_0: [float] magnitude calibration equation parameter (slope)
    @param mag_lev: [float] magnitude calibration equation parameter (intercept)
    @param x_poly: [ndarray] 1D numpy array of 12 elements containing X axis polynomial parameters
    @param y_poly: [ndarray] 1D numpy array of 12 elements containing Y axis polynomial parameters

    @return (JD_data, RA_data, dec_data, magnitude_data): [tuple of ndarrays]
        JD_data: [ndarray] julian date of each data point
        RA_data: [ndarray] right ascension of each point
        dec_data: [ndarray] declination of each point
        magnitude_data: [ndarray] array of meteor's lightcurve apparent magnitudes
    """

    # Apply field correction
    X_corrected, Y_corrected, levels_corrected = applyFieldCorrection(x_poly, y_poly, X_res, Y_res, F_scale, 
        X_data, Y_data, level_data)

    # Convert XY image coordinates to azimuth and altitude
    az_data, alt_data = XY2altAz(lat, lon, RA_d, dec_d, Ho, rot_param, X_corrected, Y_corrected)

    # Convert azimuth and altitude data to right ascension and declination
    JD_data, RA_data, dec_data = altAz2RADec(lat, lon, UT_corr, time_data, az_data, alt_data)

    # Find the beginning and ending points of the meteor and its duration in seconds
    ra_beg, ra_end = RA_data[0], RA_data[-1]
    dec_beg, dec_end = dec_data[0], dec_data[-1]
    duration = (JD_data[-1] - JD_data[0])*86400

    # Calculate magnitudes
    magnitude_data = calculateMagnitudes(levels_corrected, ra_beg, ra_end, dec_beg, dec_end, duration, 
        mag_0, mag_lev, w_pix)


    return JD_data, RA_data, dec_data, magnitude_data



def findPointTimePairs(station_obj1, station_obj2, max_dt):
    """ Find points that are closest in time. 

    ...
    @param max_dt: [float] maximum time difference between point pairs (in seconds)
    """

    max_dt = float(max_dt)/60/60/24

    point_pairs = []

    min_index = 0
    for point1 in station_obj1.points:

        min_diff = abs(point1[0] - station_obj2.points[min_index][0])

        for k, point2 in enumerate(station_obj2.points):

            # Calculate time difference between points
            diff = abs(point1[0] - point2[0])

            if diff < min_diff:
                min_index = k
                min_diff = diff

        # Check if the difference in time is too large
        if min_diff < max_dt:
            # Add points to the list
            point_pairs.append([point1, station_obj2.points[min_index]])

            print point1, station_obj2.points[min_index]

    return point_pairs



if __name__ == '__main__':

    # pp_name = 'KOP.cal'
    pp_name = 'rgn_test/platepar_CMN2010.inf'

    print parsePlatepar(pp_name)

    # Load the data from the Platepar file
    (lat, lon, elev, JD, Ho, X_res, Y_res, RA_d, dec_d, rot_param, F_scale, w_pix, mag_0, mag_lev, 
        x_poly, y_poly, station_code) = parsePlatepar(pp_name)

    # Data files from 2 stations
    station1 = 'M_2011020405RIA0001.inf'
    station2 = 'M_2011020405ZGR0001.inf'

    # Parse station information
    station_obj1 = parseInf(station1)
    station_obj2 = parseInf(station2)

    print station_obj1

    point_pairs = findPointTimePairs(station_obj1, station_obj2, 2)

    triangulated_points = []

    # Run the triangulation procedure on paired points
    for pair in point_pairs:

        jd1, ra1, dec1, _ = pair[0]
        jd2, ra2, dec2, _ = pair[1]

        # Store triangulation results
        triangulated_points.append(triangulate(pair[0][0], station_obj1.lat, station_obj1.lon, station_obj1.h, 
            ra1, dec1, station_obj2.lat, station_obj2.lon, station_obj2.h, ra2, dec2))

    print triangulated_points

    triangulated_points = np.array(triangulated_points)

    # Limit error
    error_limit = triangulated_points[:,3]
    good_indices = np.where(error_limit < 1000)

    xs = triangulated_points[:,0][good_indices]
    ys = triangulated_points[:,1][good_indices]
    zs = triangulated_points[:,2][good_indices]

    # Show triangulated points in 3D
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    ax.scatter(xs, ys, zs, c='b', marker='o')

    ax.set_xlabel('Lat')
    ax.set_ylabel('Lon')
    ax.set_zlabel('h')

    plt.show()