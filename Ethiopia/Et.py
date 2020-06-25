from datetime import datetime

import wget
import requests
from urllib import request

try:
    from StringIO import StringIO

except ImportError:
    from io import StringIO
import ee

try:
    ee.Initialize()
except Exception as e:
    ee.Authenticate()
    ee.Initialize()


def gee_to_drive(s1, s2):
    today = ee.Date(datetime.now())

    woreda = ee.FeatureCollection("users/ramcharankankanala/Final")
    gpm = ee.ImageCollection("NASA/GPM_L3/IMERG_V06")
    lstTerra8 = ee.ImageCollection("MODIS/006/MOD11A2").filterDate('2001-06-26', today)
    brdfReflect = ee.ImageCollection("MODIS/006/MCD43A4")
    brdfQA = ee.ImageCollection("MODIS/006/MCD43A2")
    # string1 = str(input('Start date:'))
    # string2 = str(input('End date:'))
    string1 = s1
    string2 = s2

    reqStartDate = ee.Date(string1)
    reqEndDate = ee.Date(string2)
    # print(reqStartDate)

    lstEarliestDate = lstTerra8.first().date();
    # print(lstEarliestDate)
    # Filter collection to dates from beginning to requested
    priorLstImgcol = lstTerra8.filterDate(lstEarliestDate, reqStartDate);
    # Get the latest (max) date of this collection of earlier images
    lstPrevMax = priorLstImgcol.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    lstStartDate = ee.Date(lstPrevMax.get('max'));
    # print('lstStartDate', lstStartDate);

    gpmAllMax = gpm.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    gpmAllEndDateTime = ee.Date(gpmAllMax.get('max'));

    gpmAllEndDate = ee.Date.fromYMD(**{
        'year': gpmAllEndDateTime.get('year'),
        'month': gpmAllEndDateTime.get('month'),
        'day': gpmAllEndDateTime.get('day')
    });

    precipStartDate = ee.Date(ee.Algorithms.If(gpmAllEndDate.millis().lt(reqStartDate.millis()),
                                               # if data ends before requested start, take last data date
                                               gpmAllEndDate,
                                               # otherwise use requested date as normal
                                               reqStartDate));
    # print('precipStartDate', precipStartDate);

    brdfAllMax = brdfReflect.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    brdfAllEndDate = ee.Date(brdfAllMax.get('max'));
    brdfStartDate = ee.Date(ee.Algorithms.If(brdfAllEndDate.millis().lt(reqStartDate.millis()),
                                             # if data ends before requested start, take last data date
                                             brdfAllEndDate,
                                             # otherwise use requested date as normal
                                             reqStartDate));
    # print('brdfStartDate', brdfStartDate);

    # Step 2: Precipitation
    # Step 2a: Precipitation filtering and dates
    # Filter gpm by date, using modified start if necessary
    gpmFiltered = gpm.filterDate(precipStartDate, reqEndDate.advance(1, 'day')).select('precipitationCal');

    # Calculate date of most recent measurement for gpm (in modified requested window)
    gpmMax = gpmFiltered.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    gpmEndDate = ee.Date(gpmMax.get('max'));
    precipEndDate = gpmEndDate;
    # print('precipEndDate ', precipEndDate);

    precipDays = precipEndDate.difference(precipStartDate, 'day');
    precipDatesPrep = ee.List.sequence(0, precipDays, 1);

    precipDatesPrep.getInfo()

    def makePrecipDates(n):
        return precipStartDate.advance(n, 'day');

    precipDates = precipDatesPrep.map(makePrecipDates);

    # precipDates.getInfo()
    def calcDailyPrecip(curdate):
        curyear = ee.Date(curdate).get('year');
        curdoy = ee.Date(curdate).getRelative('day', 'year').add(1);
        totprec = gpmFiltered.select('precipitationCal').filterDate(ee.Date(curdate),
                                                                    ee.Date(curdate).advance(1, 'day')).sum().multiply(
            0.5).rename('totprec');
        return totprec.set('doy', curdoy).set('year', curyear).set('system:time_start', curdate);

    dailyPrecipExtended = ee.ImageCollection.fromImages(precipDates.map(calcDailyPrecip));
    dailyPrecip = dailyPrecipExtended.filterDate(reqStartDate, precipEndDate.advance(1, 'day'));
    precipSummary = dailyPrecip.filterDate(reqStartDate, reqEndDate.advance(1, 'day'));

    def sumZonalPrecip(image):
        # To get the doy and year, we convert the metadata to grids and then summarize
        image2 = image.addBands([image.metadata('doy').int(), image.metadata('year').int()]);
        # Reduce by regions to get zonal means for each county
        output = image2.select(['year', 'doy', 'totprec'], ['year', 'doy', 'totprec']).reduceRegions(**{
            'collection': woreda,
            'reducer': ee.Reducer.mean(),
            'scale': 1000});
        return output;

    # Map the zonal statistics function over the filtered precip data
    precipWoreda = precipSummary.map(sumZonalPrecip);
    # Flatten the results for export
    precipFlat = precipWoreda.flatten();

    # Step 3a: Calculate LST variables
    # Filter Terra LST by altered LST start date
    lstFiltered = lstTerra8.filterDate(lstStartDate, reqEndDate.advance(8, 'day')).filterBounds(woreda).select(
        'LST_Day_1km', 'QC_Day', 'LST_Night_1km', 'QC_Night');

    def filterLstQA(image):
        qaday = image.select(['QC_Day']);
        qanight = image.select(['QC_Night']);
        dayshift = qaday.rightShift(6);
        nightshift = qanight.rightShift(6);
        daymask = dayshift.lte(2);
        nightmask = nightshift.lte(2);
        outimage = ee.Image(image.select(['LST_Day_1km', 'LST_Night_1km']));
        outmask = ee.Image([daymask, nightmask]);
        return outimage.updateMask(outmask);

    lstFilteredQA = lstFiltered.map(filterLstQA);

    def rescaleLst(image):
        lst_day = image.select('LST_Day_1km').multiply(0.02).subtract(273.15).rename('lst_day');
        lst_night = image.select('LST_Night_1km').multiply(0.02).subtract(273.15).rename('lst_night');
        lst_mean = image.expression(
            '(day + night) / 2', {
                'day': lst_day.select('lst_day'),
                'night': lst_night.select('lst_night')
            }
        ).rename('lst_mean');
        return image.addBands(lst_day).addBands(lst_night).addBands(lst_mean);

    lstVars = lstFilteredQA.map(rescaleLst);
    lstRange = lstVars.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    lstEndDate = ee.Date(lstRange.get('max')).advance(7, 'day');
    lstDays = lstEndDate.difference(lstStartDate, 'day');
    lstDatesPrep = ee.List.sequence(0, lstDays, 1);

    def makeLstDates(n):
        return lstStartDate.advance(n, 'day')

    lstDates = lstDatesPrep.map(makeLstDates)

    def calcDailyLst(curdate):
        curyear = ee.Date(curdate).get('year');
        curdoy = ee.Date(curdate).getRelative('day', 'year').add(1);
        moddoy = curdoy.divide(8).ceil().subtract(1).multiply(8).add(1);
        basedate = ee.Date.fromYMD(curyear, 1, 1);
        moddate = basedate.advance(moddoy.subtract(1), 'day');
        lst_day = lstVars.select('lst_day').filterDate(moddate, moddate.advance(1, 'day')).first().rename('lst_day');
        lst_night = lstVars.select('lst_night').filterDate(moddate, moddate.advance(1, 'day')).first().rename(
            'lst_night');
        lst_mean = lstVars.select('lst_mean').filterDate(moddate, moddate.advance(1, 'day')).first().rename('lst_mean');
        return lst_day.addBands(lst_night).addBands(lst_mean).set('doy', curdoy).set('year', curyear).set(
            'system:time_start', curdate);

    dailyLstExtended = ee.ImageCollection.fromImages(lstDates.map(calcDailyLst));
    dailyLst = dailyLstExtended.filterDate(reqStartDate, lstEndDate.advance(1, 'day'));
    lstSummary = dailyLst.filterDate(reqStartDate, reqEndDate.advance(1, 'day'));

    def sumZonalLst(image):
        # To get the doy and year, we convert the metadata to grids and then summarize
        image2 = image.addBands([image.metadata('doy').int(), image.metadata('year').int()]);
        # Reduce by regions to get zonal means for each county
        output = image2.select(['doy', 'year', 'lst_day', 'lst_night', "lst_mean"],
                               ['doy', 'year', 'lst_day', 'lst_night', 'lst_mean']).reduceRegions(**{
            'collection': woreda,
            'reducer': ee.Reducer.mean(),
            'scale': 1000});
        return output;

    # Map the zonal statistics function over the filtered lst data
    lstWoreda = lstSummary.map(sumZonalLst);
    # Flatten the results for export
    lstFlat = lstWoreda.flatten();

    # Step 4: BRDF / Spectral Indices
    # Step 4a: Calculate spectral indices
    # Filter BRDF-Adjusted Reflectance by Date

    brdfReflectVars = brdfReflect.filterDate(brdfStartDate, reqEndDate.advance(1, 'day')).filterBounds(woreda).select(
        ['Nadir_Reflectance_Band1', 'Nadir_Reflectance_Band2', 'Nadir_Reflectance_Band3', 'Nadir_Reflectance_Band4',
         'Nadir_Reflectance_Band5', 'Nadir_Reflectance_Band6', 'Nadir_Reflectance_Band7'],
        ['red', 'nir', 'blue', 'green', 'swir1', 'swir2', 'swir3']);

    # Filter BRDF QA by Date
    brdfReflectQA = brdfQA.filterDate(brdfStartDate, reqEndDate.advance(1, 'day')).filterBounds(woreda).select(
        ['BRDF_Albedo_Band_Quality_Band1', 'BRDF_Albedo_Band_Quality_Band2', 'BRDF_Albedo_Band_Quality_Band3',
         'BRDF_Albedo_Band_Quality_Band4', 'BRDF_Albedo_Band_Quality_Band5', 'BRDF_Albedo_Band_Quality_Band6',
         'BRDF_Albedo_Band_Quality_Band7', 'BRDF_Albedo_LandWaterType'],
        ['qa1', 'qa2', 'qa3', 'qa4', 'qa5', 'qa6', 'qa7', 'water']);
    idJoin = ee.Filter.equals(leftField='system:time_end', rightField='system:time_end');
    # Define the join
    innerJoin = ee.Join.inner('NBAR', 'QA');
    # Apply the join
    brdfJoined = innerJoin.apply(brdfReflectVars, brdfReflectQA, idJoin);

    def addQABands(image):
        nbar = ee.Image(image.get('NBAR'));
        qa = ee.Image(image.get('QA')).select(['qa2']);
        water = ee.Image(image.get('QA')).select(['water']);
        return nbar.addBands([qa, water]);

    brdfMerged = ee.ImageCollection(brdfJoined.map(addQABands));

    def filterBrdf(image):
        qaband = image.select(['qa2']);  # Right now, only using QA info for the NIR band
        wband = image.select(['water']);
        qamask = qaband.lte(2) and wband.eq(1);
        nir_r = image.select('nir').multiply(0.0001).rename('nir_r');
        red_r = image.select('red').multiply(0.0001).rename('red_r');
        swir1_r = image.select('swir1').multiply(0.0001).rename('swir1_r');
        swir2_r = image.select('swir2').multiply(0.0001).rename('swir2_r');
        blue_r = image.select('blue').multiply(0.0001).rename('blue_r');
        return image.addBands(nir_r).addBands(red_r).addBands(swir1_r).addBands(swir2_r).addBands(blue_r).updateMask(
            qamask);

    brdfFilteredVars = brdfMerged.map(filterBrdf);

    def calcBrdfIndices(image):
        curyear = ee.Date(image.get("system:time_start")).get('year');
        curdoy = ee.Date(image.get("system:time_start")).getRelative('day', 'year').add(1);
        ndvi = image.normalizedDifference(['nir_r', 'red_r']).rename('ndvi');
        savi = image.expression(
            '1.5 * (nir - red) / (nir + red + 0.5)', {
                'nir': image.select('nir_r'),
                'red': image.select('red_r')
            }
        ).rename('savi');
        evi = image.expression(
            '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)', {
                'nir': image.select('nir_r'),
                'red': image.select('red_r'),
                'blue': image.select('blue_r')
            }
        ).rename('evi');
        ndwi5 = image.normalizedDifference(['nir_r', 'swir1_r']).rename('ndwi5');
        ndwi6 = image.normalizedDifference(['nir_r', 'swir2_r']).rename('ndwi6');
        return image.addBands(ndvi).addBands(savi).addBands(evi).addBands(ndwi5).addBands(ndwi6).set('doy', curdoy).set(
            'year', curyear);

    brdfFilteredVars = brdfFilteredVars.map(calcBrdfIndices);
    brdfRange = brdfFilteredVars.reduceColumns(ee.Reducer.max(), ["system:time_start"]);
    brdfEndDate = ee.Date(brdfRange.get('max'));
    brdfDays = brdfEndDate.difference(brdfStartDate, 'day');
    brdfDatesPrep = ee.List.sequence(0, brdfDays, 1);

    def makeBrdfDates(n):
        return brdfStartDate.advance(n, 'day');

    brdfDates = brdfDatesPrep.map(makeBrdfDates);

    def calcDailyBrdf(curdate):
        curyear = ee.Date(curdate).get('year');
        curdoy = ee.Date(curdate).getRelative('day', 'year').add(1);
        brdfTemp = brdfFilteredVars.filterDate(ee.Date(curdate), ee.Date(curdate).advance(1, 'day'));
        brdfSize = brdfTemp.size();
        outimg = ee.Image(ee.Algorithms.If(brdfSize.eq(0),
                                           ee.Image.constant(0).selfMask()
                                           .addBands(ee.Image.constant(0).selfMask())
                                           .addBands(ee.Image.constant(0).selfMask())
                                           .addBands(ee.Image.constant(0).selfMask())
                                           .addBands(ee.Image.constant(0).selfMask())
                                           .rename(['ndvi', 'evi', 'savi', 'ndwi5', 'ndwi6'])
                                           .set('doy', curdoy)
                                           .set('year', curyear)
                                           .set('system:time_start', curdate),
                                           brdfTemp.first()));
        return outimg;

    dailyBrdfExtended = ee.ImageCollection.fromImages(brdfDates.map(calcDailyBrdf));
    dailyBrdf = dailyBrdfExtended.filterDate(reqStartDate, brdfEndDate.advance(1, 'day'));
    brdfSummary = dailyBrdf.filterDate(reqStartDate, reqEndDate.advance(1, 'day'));

    # Function to calculate zonal statistics for spectral indices by county
    def sumZonalBrdf(image):
        # To get the doy and year, we convert the metadata to grids and then summarize
        image2 = image.addBands([image.metadata('doy').int(), image.metadata('year').int()]);
        # educe by regions to get zonal means for each county
        output = image2.select(['doy', 'year', 'ndvi', 'savi', 'evi', 'ndwi5', 'ndwi6'],
                               ['doy', 'year', 'ndvi', 'savi', 'evi', 'ndwi5', 'ndwi6']).reduceRegions(**{
            'collection': woreda,
            'reducer': ee.Reducer.mean(),
            'scale': 1000});
        return output;

    # ap the zonal statistics function over the filtered spectral index data
    brdfWoreda = brdfSummary.map(sumZonalBrdf);
    # latten the results for export
    brdfFlat = brdfWoreda.flatten();

    def exportSummaries():
        precipURL = precipFlat.getDownloadURL(**{'filename': string1 + ' ' + 'to'+ ' ' + string2 + 'precipFlat.csv',
                                                 'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year',
                                                               'totprec']})
        lstURL = lstFlat.getDownloadURL(**{'filename': string1 + ' ' + 'to' + ' ' + string2 + 'lstFlat.csv',
                                           'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year',
                                                         'lst_day', 'lst_night', 'lst_mean']})
        brdfURL = brdfFlat.getDownloadURL(**{'filename': string1 + ' ' + 'to' + ' ' + string2 + 'brdfFlat.csv',
                                             'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year',
                                                           'ndvi', 'savi', 'evi', 'ndwi5', 'ndwi6']})
        downloadlist = [precipURL,lstURL,brdfURL]
        print('precipURL:',precipURL)
        print('lstURL:',lstURL)
        print('brdfURL:',brdfURL)
        return downloadlist

    def downloadsummary():
        link = exportSummaries()
        url1 = link[0]
        url2 = link[1]
        url3 = link[2]
        print('precipURL:', url1)
        print('lstURL:', url2)
        print('brdfURL:', url3)
        wget.download(link[0], string1 + 'to' + string2 + 'precipFlat.csv')
        wget.download(link[1], string1 + 'to' + string2 + 'lstFlat.csv')
        wget.download(link[2], string1 + 'to' + string2 + 'brdfFlat.csv')
        print("Data downloaded to local drive")

    def datatolocaldrive():
        link = exportSummaries()
        url1 = link[0]
        url2 = link[1]
        url3 = link[2]
        print('precipURL:', url1)
        print('lstURL:', url2)
        print('brdfURL:', url3)
        r = requests.get(url1,allow_redirects=True)

        with open(string1 + 'to' + string2 + 'precipFlat.csv', 'wb') as f:
            f.write(r.content)

        r1 = requests.get(url2,allow_redirects=True)

        with open(string1 + 'to' + string2 + 'lstFlat.csv', 'wb') as f1:
            f1.write(r1.content)

        r2 = requests.get(url3,allow_redirects=True)

        with open(string1 + 'to' + string2 + 'brdfFlat.csv', 'wb') as f2:
            f2.write(r2.content)

    def datatolocal():
        link = exportSummaries()
        url1 = link[0]
        url2 = link[1]
        url3 = link[2]
        print('precipURL:', url1)
        print('lstURL:', url2)
        print('brdfURL:', url3)
        request.urlretrieve(url1, string1 + 'to' + string2 + 'precipFlat.csv')
        request.urlretrieve(url2, string1 + 'to' + string2 + 'lstFlat.csv')
        request.urlretrieve(url3, string1 + 'to' + string2 + 'brdfFlat.csv')



    def ExportToDrive():
        props1 = {'driveFolder': 'Ethiopiadata', 'driveFileNamePrefix': 'precip' + string1 + 'to' + string2,
                  'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year', 'totprec'],
                  'fileFormat': 'CSV'}
        task1 = ee.batch.Export.table(precipFlat, 'Export_precip' + string1 + 'to' + string2, props1)
        props2 = {'driveFolder': 'Ethiopiadata', 'driveFileNamePrefix': 'lst' + string1 + 'to' + string2,
                  'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year', 'lst_day', 'lst_night',
                                "lst_mean"], 'fileFormat': 'CSV'}
        task2 = ee.batch.Export.table(lstFlat, 'Export_lst' + string1 + 'to' + string2, props2)
        props3 = {'driveFolder': 'Ethiopiadata', 'driveFileNamePrefix': 'brdf' + string1 + 'to' + string2,
                  'selectors': ['NewPCODE', 'R_NAME', 'W_NAME', 'Z_NAME', 'doy', 'year', 'ndvi', 'savi', 'evi', 'ndwi5',
                                'ndwi6'],
                  'fileFormat': 'CSV'}
        task3 = ee.batch.Export.table(brdfFlat, 'Export_brdf' + string1 + 'to' + string2, props3)
        task1.start()
        task2.start()
        task3.start()
        print("Data will Export to google drive in to Ethiopiadata folder which will take a while depending on date range:--------")


    #downloadsummary()
    ExportToDrive()
    exportSummaries()
    #datatolocaldrive()
    #datatolocal()

#all('2009-01-01','2010-01-01')
# def main():
# summary = exportSummaries()
#


# print('precipURL',link[0])
# print('lstURL',link[1])
# print('brdfURL',link[2])
