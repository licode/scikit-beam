# ######################################################################
# Copyright (c) 2014, Brookhaven Science Associates, Brookhaven        #
# National Laboratory. All rights reserved.                            #
#                                                                      #
# @author: Li Li (lili@bnl.gov)                                        #
# created on 09/10/2014                                                #
#                                                                      #
# Original code:                                                       #
# @author: Mirna Lerotic, 2nd Look Consulting                          #
#         http://www.2ndlookconsulting.com/                            #
# Copyright (c) 2013, Stefan Vogt, Argonne National Laboratory         #
# All rights reserved.                                                 #
#                                                                      #
# Redistribution and use in source and binary forms, with or without   #
# modification, are permitted provided that the following conditions   #
# are met:                                                             #
#                                                                      #
# * Redistributions of source code must retain the above copyright     #
#   notice, this list of conditions and the following disclaimer.      #
#                                                                      #
# * Redistributions in binary form must reproduce the above copyright  #
#   notice this list of conditions and the following disclaimer in     #
#   the documentation and/or other materials provided with the         #
#   distribution.                                                      #
#                                                                      #
# * Neither the name of the Brookhaven Science Associates, Brookhaven  #
#   National Laboratory nor the names of its contributors may be used  #
#   to endorse or promote products derived from this software without  #
#   specific prior written permission.                                 #
#                                                                      #
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS  #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT    #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS    #
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE       #
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT,           #
# INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES   #
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR   #
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)   #
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,  #
# STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OTHERWISE) ARISING   #
# IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE   #
# POSSIBILITY OF SUCH DAMAGE.                                          #
########################################################################

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import numpy as np
from scipy.optimize import nnls
import six
import copy

import logging
logger = logging.getLogger(__name__)

from skxray.constants.api import XrfElement as Element
from skxray.fitting.lineshapes import gaussian
from skxray.fitting.models import (ComptonModel, ElasticModel,
                                   _gen_class_docs)
from skxray.fitting.base.parameter_data import get_para
from skxray.fitting.background import snip_method
from lmfit import Model


# emission line energy above 1 keV
k_line = ['Na', 'Mg', 'Al', 'Si', 'P', 'S', 'Cl', 'Ar', 'K', 'Ca', 'Sc', 'Ti', 'V', 'Cr',
          'Mn', 'Fe', 'Co', 'Ni', 'Cu', 'Zn', 'Ga', 'Ge', 'As', 'Se', 'Br', 'Kr', 'Rb',
          'Sr', 'Y', 'Zr', 'Nb', 'Mo', 'Tc', 'Ru', 'Rh', 'Pd', 'Ag', 'Cd',
          'In', 'Sn', 'Sb', 'Te', 'I']

l_line = ['Ga_L', 'Ge_L', 'As_L', 'Se_L', 'Br_L', 'Kr_L', 'Rb_L', 'Sr_L', 'Y_L', 'Zr_L', 'Nb_L',
          'Mo_L', 'Tc_L', 'Ru_L', 'Rh_L', 'Pd_L', 'Ag_L', 'Cd_L', 'In_L', 'Sn_L', 'Sb_L', 'Te_L',
          'I_L', 'Xe_L', 'Cs_L', 'Ba_L', 'La_L', 'Ce_L', 'Pr_L', 'Nd_L', 'Pm_L', 'Sm_L', 'Eu_L',
          'Gd_L', 'Tb_L', 'Dy_L', 'Ho_L', 'Er_L', 'Tm_L', 'Yb_L', 'Lu_L', 'Hf_L', 'Ta_L', 'W_L',
          'Re_L', 'Os_L', 'Ir_L', 'Pt_L', 'Au_L', 'Hg_L', 'Tl_L', 'Pb_L', 'Bi_L', 'Po_L', 'At_L',
          'Rn_L', 'Fr_L', 'Ac_L', 'Th_L', 'Pa_L', 'U_L', 'Np_L', 'Pu_L', 'Am_L']

m_line = ['Hf_M', 'Ta_M', 'W_M', 'Re_M', 'Os_M', 'Ir_M', 'Pt_M', 'Au_M', 'Hg_M', 'TL_M', 'Pb_M', 'Bi_M',
          'Sm_M', 'Eu_M', 'Gd_M', 'Tb_M', 'Dy_M', 'Ho_M', 'Er_M', 'Tm_M', 'Yb_M', 'Lu_M', 'Th_M', 'Pa_M', 'U_M']

k_list = ['ka1', 'ka2', 'kb1', 'kb2']
l_list = ['la1', 'la2', 'lb1', 'lb2', 'lb3', 'lb4', 'lb5',
          'lg1', 'lg2', 'lg3', 'lg4', 'll', 'ln']


def element_peak_xrf(x, area, center,
                     delta_center, delta_sigma,
                     ratio, ratio_adjust,
                     fwhm_offset, fwhm_fanoprime,
                     e_offset, e_linear, e_quadratic,
                     epsilon=2.96):
    """
    This is a function to construct xrf element peak, which is based on gauss profile,
    but more specific requirements need to be considered. For instance, the standard
    deviation is replaced by global fitting parameters, and energy calibration on x is
    taken into account.

    Parameters
    ----------
    x : array
        independent variable, channel number instead of energy
    area : float
        area of gaussian function
    center : float
        center position
    delta_center : float
        adjustment to center position
    delta_sigma : float
        adjustment to standard deviation
    ratio : float
        branching ratio
    ratio_adjust : float
        value used to adjust peak height
    fwhm_offset : float
        global fitting parameter for peak width
    fwhm_fanoprime : float
        global fitting parameter for peak width
    e_offset : float
        offset of energy calibration
    e_linear : float
        linear coefficient in energy calibration
    e_quadratic : float
        quadratic coefficient in energy calibration

    Returns
    -------
    array:
        gaussian peak profile
    """
    def get_sigma(center):
        temp_val = 2 * np.sqrt(2 * np.log(2))
        return np.sqrt((fwhm_offset/temp_val)**2 + center*epsilon*fwhm_fanoprime)

    x = e_offset + x * e_linear + x**2 * e_quadratic

    return gaussian(x, area, center+delta_center,
                    delta_sigma+get_sigma(center)) * ratio * ratio_adjust


class ElementModel(Model):

    __doc__ = _gen_class_docs(element_peak_xrf)

    def __init__(self, *args, **kwargs):
        super(ElementModel, self).__init__(element_peak_xrf, *args, **kwargs)
        self.set_param_hint('epsilon', value=2.96, vary=False)


def _set_parameter_hint(param_name, input_dict, input_model,
                        log_option=False):
    """
    Set parameter hint information to lmfit model from input dict.

    Parameters
    ----------
    param_name : str
        parameter used for fitting
    input_dict : dict
        all the initial values and constraints for given parameters
    input_model : object
        model object used in lmfit
    log_option : bool
        option for logger
    """
    if input_dict['bound_type'] == 'none':
        input_model.set_param_hint(name=param_name, value=input_dict['value'], vary=True)
    elif input_dict['bound_type'] == 'fixed':
        input_model.set_param_hint(name=param_name, value=input_dict['value'], vary=False)
    elif input_dict['bound_type'] == 'lohi':
        input_model.set_param_hint(name=param_name, value=input_dict['value'], vary=True,
                                   min=input_dict['min'], max=input_dict['max'])
    elif input_dict['bound_type'] == 'lo':
        input_model.set_param_hint(name=param_name, value=input_dict['value'], vary=True,
                                   min=input_dict['min'])
    elif input_dict['bound_type'] == 'hi':
        input_model.set_param_hint(name=param_name, value=input_dict['value'], vary=True,
                                   min=input_dict['max'])
    else:
        raise ValueError("could not set values for {0}".format(param_name))
    if log_option:
        logger.debug(' {0} bound type: {1}, value: {2}, range: {3}'.
                    format(param_name, input_dict['bound_type'], input_dict['value'],
                           [input_dict['min'], input_dict['max']]))


def update_parameter_dict(xrf_parameter, fit_results):
    """
    Update fitting parameters dictionary according to given fitting results,
    usually obtained from previous run.

    Parameters
    ----------
    xrf_parameter : dict
        saving all the fitting values and their bounds
    fit_results : object
        ModelFit object from lmfit
    """
    for k, v in six.iteritems(xrf_parameter):
        if fit_results.values.has_key(k):
            xrf_parameter[str(k)]['value'] = fit_results.values[str(k)]


def set_parameter_bound(xrf_parameter, bound_option):
    """
    Update the default value of bounds.

    Parameters
    ----------
    xrf_parameter : dict
        saving all the fitting values and their bounds
    bound_option : str
        define bound type
    """
    for k, v in six.iteritems(xrf_parameter):
        if k == 'non_fitting_values':
            continue
        v['bound_type'] = v[str(bound_option)]


#This dict is used to update the current parameter dict to dynamically change the input data
# and do the fitting. The user can adjust parameters such as position, width, area or branching ratio.
element_dict = {
    'pos': {"bound_type": "fixed", "min": -0.005, "max": 0.005, "value": 0, "fit_with_tail": "fixed",
            "free_more": "fixed", "adjust_element": "fixed", "e_calibration": "fixed", "linear": "fixed"},
    'width': {"bound_type": "fixed", "min": -0.02, "max": 0.02, "value": 0.0, "fit_with_tail": "fixed",
              "free_more": "fixed", "adjust_element": "fixed", "e_calibration": "fixed", "linear": "fixed"},
    'area': {"bound_type": "none", "min": 0, "max": 1e9, "value": 1000, "fit_with_tail": "fixed",
             "free_more": "none", "adjust_element": "fixed", "e_calibration": "fixed", "linear": "none"},
    'ratio': {"bound_type": "fixed", "min": 0.1, "max": 5.0, "value": 1.0, "fit_with_tail": "fixed",
              "free_more": "fixed", "adjust_element": "fixed", "e_calibration":"fixed", "linear":"fixed"}
}


# def get_L_line(prop_name, element):
#     #l_list = ['la1', 'la2', 'lb1', 'lb2', 'lb3', 'lb4', 'lb5',
#     #          'lg1', 'lg2', 'lg3', 'lg4', 'll', 'ln']
#     l_list = ['la1', 'la2', 'lb1', 'lb2', 'lb3',
#               'lg1', 'lg2', 'll']
#     return [str(prop_name)+'-'+str(element)+'-'+str(item)
#            for item in l_list]


class ParamController(object):

    def __init__(self, xrf_parameter):
        """
        Update element peak information in parameter dictionary.
        This is an important step in dynamical fitting. The

        Parameters
        ----------
        xrf_parameter : dict
            saving all the fitting values and their bounds
        """
        self.pre_parameter = xrf_parameter
        self.new_parameter = copy.deepcopy(xrf_parameter)
        self.element_list = xrf_parameter['non_fitting_values']['element_list'].split(', ')
        self.element_line_name = self.get_all_lines(xrf_parameter['coherent_sct_energy']['value'],
                                                    self.element_list)

    def get_all_lines(self, incident_energy, ename_list):
        all_line = []
        for v in ename_list:
            activated_line = self.get_actived_line(incident_energy, v)
            if activated_line:
                all_line += activated_line
        return all_line

    def get_actived_line(self, incident_energy, ename):
        """
        Collect all the actived lines for given element.
        """
        line_list = []
        if ename in k_line:
            e = Element(ename)
            if e.cs(incident_energy)['ka1'] == 0:
                return

            for num, item in enumerate(e.emission_line.all[:4]):
                line_name = item[0]
                val = item[1]
                if e.cs(incident_energy)[line_name] == 0:
                    continue
                line_list.append(str(ename)+'_'+str(line_name))
            return line_list

        elif ename in l_line:
            ename = ename.split('_')[0]
            e = Element(ename)
            if e.cs(incident_energy)['la1'] == 0:
                return

            for num, item in enumerate(e.emission_line.all[4:-4]):
                line_name = item[0]
                val = item[1]
                if e.cs(incident_energy)[line_name] == 0:
                    continue
                line_list.append(str(ename)+'_'+str(line_name))
            return line_list

    def create_full_param(self):
        """
        Add all element information, such as pos, width, ratio into parameter dict.
        """
        for v in self.element_list:
            self.set_area(v)
            self.set_position(v)
            self.set_ratio(v)
            self.set_width(v)

    def update_single_item(self, **kwargs):
        for k, v in six.iteritems(kwargs):
            self.new_parameter[k]['value'] = v

    def set_bound_type(self, bound_option):
        """
        Update the default value of bounds.

        Parameters
        ----------
        bound_option : str
            define bound type
        """
        set_parameter_bound(self.new_parameter, bound_option)

    def update_with_fit_result(self, fit_results):
        """
        Update fitting parameters dictionary according to given fitting results,
        usually obtained from previous run.

        Parameters
        ----------
        fit_results : object
            ModelFit object from lmfit
        """
        update_parameter_dict(self.new_parameter, fit_results)

    def update_element_prop(self, element_list, **kwargs):
        """
        Update element properties, such as pos, width, area and ratio.

        Parameters
        ----------
        element_list : list
            define which element to update
        kws : dict
            define what kind of property to change

        Returns
        -------
        dict : updated value
        """
        for k, v in six.iteritems(kwargs):
            if k == 'pos':
                func = self.set_position
            elif k == 'width':
                func = self.set_width
            elif k == 'area':
                func = self.set_area
            elif k == 'ratio':
                func = self.set_ratio
            else:
                raise ValueError('Please define either pos, width, area or ratio.')

            for element in element_list:
                func(element, option=v)
        #return self.new_parameter

    def set_position(self, item, option=None):
        """
        Parameters
        ----------
        item : str
            element name
        option : str, optional
            way to control position
        """
        if item in k_line:
            pos_list = k_list
        elif item in l_line:
            item = item.split('_')[0]
            pos_list = l_list

        pos_list = [str(item)+'_'+str(v).lower() for v in pos_list]

        for linename in pos_list:
            # check if the line is activated
            if linename not in self.element_line_name:
                continue
            new_pos = element_dict['pos'].copy()
            if option:
                new_pos['adjust_element'] = option
            self.new_parameter.update({str(linename)+'_delta_center': new_pos})

    def set_width(self, item, option=None):
        """
        Parameters
        ----------
        item : str
            element name
        option : str, optional
            Control peak width.
        """
        if item in k_line:
            data_list = k_list
        elif item in l_line:
            item = item.split('_')[0]
            data_list = l_list

        data_list = [str(item)+'_'+str(v).lower() for v in data_list]

        for linename in data_list:
            # check if the line is activated
            if linename not in self.element_line_name:
                continue
            new_width = element_dict['width'].copy()
            if option:
                new_width['adjust_element'] = option
            self.new_parameter.update({str(linename)+'_delta_sigma': new_width})

    def set_area(self, item, option=None):
        """
        Only the primary peak intensity is adjusted.

        Parameters
        ----------
        item : str
            element name
        option : str, optional
            way to control area
        """
        if item in k_line:
            area_list = [str(item)+"_ka1_area"]
        elif item in l_line:
            item = item.split('_')[0]
            area_list = [str(item)+"_la1_area"]
        elif item in m_line:
            item = item.split('_')[0]
            area_list = [str(item)+"_ma1_area"]


        for linename in area_list:
            new_area = element_dict['area'].copy()
            if option:
                new_area['adjust_element'] = option
            self.new_parameter.update({linename: new_area})

    def set_ratio(self, item, option=None):
        """
        Only adjust lines after the the primary one.

        Parameters
        ----------
        item : str
            element name
        option : str, optional
            way to control branching ratio
        """
        if item in k_line:
            data_list = k_list[1:]
        elif item in l_line:
            item = item.split('_')[0]
            data_list = l_list[1:]

        data_list = [str(item)+'_'+str(v).lower() for v in data_list]

        for linename in data_list:
            if linename not in self.element_line_name:
                continue
            new_val = element_dict['ratio'].copy()
            if option:
                new_val['adjust_element'] = option
            self.new_parameter.update({str(linename)+'_ratio_adjust': new_val})


def get_sum_area(element_name, result_val):
    """
    Return the total area for given element.

    Parameters
    ----------
    element_name : str
        name of given element
    result_val : obj
        result obj from lmfit to save all the fitting results

    Returns
    -------
    float
        the total area
    """
    def get_value(result_val, element_name, line_name):
        return result_val.values[str(element_name)+'_'+line_name+'_area'] * \
               result_val.values[str(element_name)+'_'+line_name+'_ratio'] * \
               result_val.values[str(element_name)+'_'+line_name+'_ratio_adjust']

    if element_name in k_line:
        sum = get_value(result_val, element_name, 'ka1') + \
              get_value(result_val, element_name, 'ka2') + \
              get_value(result_val, element_name, 'kb1')
        if result_val.values.has_key(str(element_name)+'_kb2_area'):
            sum += get_value(result_val, element_name, 'kb2')
    return sum


class ModelSpectrum(object):

    def __init__(self, xrf_parameter):
        """
        Parameters
        ----------
        xrf_parameter : dict
            saving all the fitting values and their bounds
        """
        self.parameter = xrf_parameter
        self.parameter_default = get_para()
        self._config()

    def _config(self):
        non_fit = self.parameter['non_fitting_values']
        if non_fit.has_key('element_list'):
            if ',' in non_fit['element_list']:
                self.element_list = non_fit['element_list'].split(', ')
            else:
                self.element_list = non_fit['element_list'].split()
            self.element_list = [item.strip() for item in self.element_list]
        else:
            logger.critical(' No element is selected for fitting!')

        self.incident_energy = self.parameter['coherent_sct_energy']['value']
        self.setComptonModel()
        self.setElasticModel()

    def setComptonModel(self):
        """
        setup parameters related to Compton model
        """
        compton = ComptonModel()

        compton_list = ['coherent_sct_energy', 'compton_amplitude',
                        'compton_angle', 'fwhm_offset', 'fwhm_fanoprime',
                        'e_offset', 'e_linear', 'e_quadratic',
                        'compton_gamma', 'compton_f_tail',
                        'compton_f_step', 'compton_fwhm_corr',
                        'compton_hi_gamma', 'compton_hi_f_tail']

        logger.debug(' ###### Started setting up parameters for compton model. ######')
        for name in compton_list:
            if name in self.parameter.keys():
                _set_parameter_hint(name, self.parameter[name], compton)
            else:
                _set_parameter_hint(name, self.parameter_default[name], compton)
        logger.debug(' Finished setting up parameters for compton model.')

        self.compton_param = compton.make_params()
        self.compton = compton

    def setElasticModel(self):
        """
        setup parameters related to Elastic model
        """
        elastic = ElasticModel(prefix='elastic_')

        item = 'coherent_sct_amplitude'
        if item in self.parameter.keys():
            _set_parameter_hint(item, self.parameter[item], elastic)
        else:
            _set_parameter_hint(item, self.parameter_default[item], elastic)

        logger.debug(' ###### Started setting up parameters for elastic model. ######')

        # set constraints for the following global parameters
        elastic.set_param_hint('e_offset', value=self.compton_param['e_offset'].value,
                               expr='e_offset')
        #elastic.set_param_hint('e_offset', expr='e_offset')
        elastic.set_param_hint('e_linear', value=self.compton_param['e_linear'].value,
                               expr='e_linear')
        elastic.set_param_hint('e_quadratic', value=self.compton_param['e_quadratic'].value,
                               expr='e_quadratic')
        elastic.set_param_hint('fwhm_offset', value=self.compton_param['fwhm_offset'].value,
                               expr='fwhm_offset')
        elastic.set_param_hint('fwhm_fanoprime', value=self.compton_param['fwhm_fanoprime'].value,
                               expr='fwhm_fanoprime')
        elastic.set_param_hint('coherent_sct_energy', value=self.compton_param['coherent_sct_energy'].value,
                               expr='coherent_sct_energy')
        logger.debug(' Finished setting up parameters for elastic model.')
        self.elastic = elastic

    def setElementModel(self, ename, default_area=1e5):
        """
        Construct element model.

        Parameters
        ----------
        ename : str
            element model
        """

        incident_energy = self.incident_energy
        parameter = self.parameter

        element_mod = None

        if ename in k_line:
            e = Element(ename)
            if e.cs(incident_energy)['ka1'] == 0:
                logger.debug(' {0} Ka emission line is not activated '
                            'at this energy {1}'.format(ename, incident_energy))
                return

            logger.debug(' --- Started building {0} peak. ---'.format(ename))

            for num, item in enumerate(e.emission_line.all[:4]):
                line_name = item[0]
                val = item[1]

                if e.cs(incident_energy)[line_name] == 0:
                    continue

                gauss_mod = ElementModel(prefix=str(ename)+'_'+str(line_name)+'_')
                gauss_mod.set_param_hint('e_offset', value=self.compton_param['e_offset'].value,
                                         expr='e_offset')
                gauss_mod.set_param_hint('e_linear', value=self.compton_param['e_linear'].value,
                                         expr='e_linear')
                gauss_mod.set_param_hint('e_quadratic', value=self.compton_param['e_quadratic'].value,
                                         expr='e_quadratic')
                gauss_mod.set_param_hint('fwhm_offset', value=self.compton_param['fwhm_offset'].value,
                                         expr='fwhm_offset')
                gauss_mod.set_param_hint('fwhm_fanoprime', value=self.compton_param['fwhm_fanoprime'].value,
                                         expr='fwhm_fanoprime')

                if line_name == 'ka1':
                    gauss_mod.set_param_hint('area', value=default_area, vary=True, min=0)
                    gauss_mod.set_param_hint('delta_center', value=0, vary=False)
                    gauss_mod.set_param_hint('delta_sigma', value=0, vary=False)
                elif line_name == 'ka2':
                    gauss_mod.set_param_hint('area', value=default_area, vary=True,
                                             expr=str(ename)+'_ka1_'+'area')
                    gauss_mod.set_param_hint('delta_sigma', value=0, vary=False,
                                             expr=str(ename)+'_ka1_'+'delta_sigma')
                    gauss_mod.set_param_hint('delta_center', value=0, vary=False,
                                             expr=str(ename)+'_ka1_'+'delta_center')
                else:
                    gauss_mod.set_param_hint('area', value=default_area, vary=True,
                                             expr=str(ename)+'_ka1_'+'area')
                    gauss_mod.set_param_hint('delta_center', value=0, vary=False)
                    gauss_mod.set_param_hint('delta_sigma', value=0, vary=False)

                #gauss_mod.set_param_hint('delta_center', value=0, vary=False)
                #gauss_mod.set_param_hint('delta_sigma', value=0, vary=False)

                area_name = str(ename)+'_'+str(line_name)+'_area'
                if parameter.has_key(area_name):
                    _set_parameter_hint(area_name, parameter[area_name],
                                        gauss_mod, log_option=True)

                gauss_mod.set_param_hint('center', value=val, vary=False)
                ratio_v = e.cs(incident_energy)[line_name]/e.cs(incident_energy)['ka1']
                gauss_mod.set_param_hint('ratio', value=ratio_v, vary=False)
                gauss_mod.set_param_hint('ratio_adjust', value=1, vary=False)
                logger.debug(' {0} {1} peak is at energy {2} with'
                            ' branching ratio {3}.'. format(ename, line_name, val, ratio_v))

                # position needs to be adjusted
                pos_name = ename+'_'+str(line_name)+'_delta_center'
                if parameter.has_key(pos_name):
                    _set_parameter_hint('delta_center', parameter[pos_name],
                                        gauss_mod, log_option=True)

                # width needs to be adjusted
                width_name = ename+'_'+str(line_name)+'_delta_sigma'
                if parameter.has_key(width_name):
                    _set_parameter_hint('delta_sigma', parameter[width_name],
                                        gauss_mod, log_option=True)

                # branching ratio needs to be adjusted
                ratio_name = ename+'_'+str(line_name)+'_ratio_adjust'
                if parameter.has_key(ratio_name):
                    _set_parameter_hint('ratio_adjust', parameter[ratio_name],
                                        gauss_mod, log_option=True)

                #mod = mod + gauss_mod
                if element_mod:
                    element_mod += gauss_mod
                else:
                    element_mod = gauss_mod
            logger.debug(' Finished building element peak for {0}'.format(ename))

        elif ename in l_line:
            ename = ename.split('_')[0]
            e = Element(ename)
            if e.cs(incident_energy)['la1'] == 0:
                logger.debug('{0} La1 emission line is not activated '
                            'at this energy {1}'.format(ename, incident_energy))
                return

            for num, item in enumerate(e.emission_line.all[4:-4]):

                line_name = item[0]
                val = item[1]

                if e.cs(incident_energy)[line_name] == 0:
                    continue

                gauss_mod = ElementModel(prefix=str(ename)+'_'+str(line_name)+'_')

                gauss_mod.set_param_hint('e_offset', value=self.compton_param['e_offset'].value,
                                         expr='e_offset')
                gauss_mod.set_param_hint('e_linear', value=self.compton_param['e_linear'].value,
                                         expr='e_linear')
                gauss_mod.set_param_hint('e_quadratic', value=self.compton_param['e_quadratic'].value,
                                         expr='e_quadratic')
                gauss_mod.set_param_hint('fwhm_offset', value=self.compton_param['fwhm_offset'].value,
                                         expr='fwhm_offset')
                gauss_mod.set_param_hint('fwhm_fanoprime', value=self.compton_param['fwhm_fanoprime'].value,
                                         expr='fwhm_fanoprime')

                if line_name == 'la1':
                    gauss_mod.set_param_hint('area', value=default_area, vary=True)
                                         #expr=gauss_mod.prefix+'ratio_val * '+str(ename)+'_la1_'+'area')
                else:
                    gauss_mod.set_param_hint('area', value=default_area, vary=True,
                                             expr=str(ename)+'_la1_'+'area')

                gauss_mod.set_param_hint('center', value=val, vary=False)
                gauss_mod.set_param_hint('sigma', value=1, vary=False)
                gauss_mod.set_param_hint('ratio',
                                         value=e.cs(incident_energy)[line_name]/e.cs(incident_energy)['la1'],
                                         vary=False)

                gauss_mod.set_param_hint('delta_center', value=0, vary=False)
                gauss_mod.set_param_hint('delta_sigma', value=0, vary=False)
                gauss_mod.set_param_hint('ratio_adjust', value=1, vary=False)

                # position needs to be adjusted
                #if ename in pos_adjust:
                #    pos_name = 'pos-'+ename+'-'+str(line_name)
                #    if parameter.has_key(pos_name):
                #        _set_parameter_hint('delta_center', parameter[pos_name],
                #                            gauss_mod, log_option=True)
                pos_name = ename+'_'+str(line_name)+'_delta_center'
                if parameter.has_key(pos_name):
                    _set_parameter_hint('delta_center', parameter[pos_name],
                                        gauss_mod, log_option=True)

                # width needs to be adjusted
                #if ename in width_adjust:
                #    width_name = 'width-'+ename+'-'+str(line_name)
                #    if parameter.has_key(width_name):
                #        _set_parameter_hint('delta_sigma', parameter[width_name],
                #                            gauss_mod, log_option=True)
                width_name = ename+'_'+str(line_name)+'_delta_sigma'
                if parameter.has_key(width_name):
                    _set_parameter_hint('delta_sigma', parameter[width_name],
                                        gauss_mod, log_option=True)

                # branching ratio needs to be adjusted
                #if ename in ratio_adjust:
                #    ratio_name = 'ratio-'+ename+'-'+str(line_name)
                #    if parameter.has_key(ratio_name):
                #        _set_parameter_hint('ratio_adjust', parameter[ratio_name],
                #                            gauss_mod, log_option=True)
                ratio_name = ename+'_'+str(line_name)+'_ratio_adjust'
                if parameter.has_key(ratio_name):
                    _set_parameter_hint('ratio_adjust', parameter[ratio_name],
                                        gauss_mod, log_option=True)
                if element_mod:
                    element_mod += gauss_mod
                else:
                    element_mod = gauss_mod

        elif ename in m_line:
            ename = ename.split('_')[0]
            e = Element(ename)
            if e.cs(incident_energy)['ma1'] == 0:
                logger.debug('{0} ma1 emission line is not activated '
                            'at this energy {1}'.format(ename, incident_energy))
                return

            for num, item in enumerate(e.emission_line.all[-4:]):

                line_name = item[0]
                val = item[1]

                if e.cs(incident_energy)[line_name] == 0:
                    continue

                #if gauss_mod:
                #    gauss_mod = gauss_mod + ElementModel(prefix=str(ename)+'_'+str(line_name)+'_')
                #else:
                gauss_mod = ElementModel(prefix=str(ename)+'_'+str(line_name)+'_')

                gauss_mod.set_param_hint('e_offset', value=self.compton_param['e_offset'].value,
                                         expr='e_offset')
                gauss_mod.set_param_hint('e_linear', value=self.compton_param['e_linear'].value,
                                         expr='e_linear')
                gauss_mod.set_param_hint('e_quadratic', value=self.compton_param['e_quadratic'].value,
                                         expr='e_quadratic')
                gauss_mod.set_param_hint('fwhm_offset', value=self.compton_param['fwhm_offset'].value,
                                         expr='fwhm_offset')
                gauss_mod.set_param_hint('fwhm_fanoprime', value=self.compton_param['fwhm_fanoprime'].value,
                                         expr='fwhm_fanoprime')

                if line_name == 'ma1':
                    gauss_mod.set_param_hint('area', value=default_area, vary=True)
                else:
                    gauss_mod.set_param_hint('area', value=default_area, vary=True,
                                             expr=str(ename)+'_ma1_'+'area')

                gauss_mod.set_param_hint('center', value=val, vary=False)
                gauss_mod.set_param_hint('sigma', value=1, vary=False)
                gauss_mod.set_param_hint('ratio',
                                         value=0.1, #e.cs(incident_energy)[line_name]/e.cs(incident_energy)['ma1'],
                                         vary=False)

                gauss_mod.set_param_hint('delta_center', value=0, vary=False)
                gauss_mod.set_param_hint('delta_sigma', value=0, vary=False)
                gauss_mod.set_param_hint('ratio_adjust', value=1, vary=False)

                if element_mod:
                    element_mod += gauss_mod
                else:
                    element_mod = gauss_mod

        return element_mod

    def model_spectrum(self):
        """
        Put all models together to form a spectrum.
        """
        self.mod = self.compton + self.elastic

        for ename in self.element_list:
            self.mod += self.setElementModel(ename)

    def model_fit(self, x, y, w=None, method='leastsq', **kws):
        """
        Parameters
        ----------
        x : array
            independent variable
        y : array
            intensity
        w : array, optional
            weight for fitting
        method : str
            default as leastsq
        kws : dict
            fitting criteria, such as max number of iteration

        Returns
        -------
        result object from lmfit
        """

        pars = self.mod.make_params()
        result = self.mod.fit(y, pars, x=x, weights=w,
                              method=method, fit_kws=kws)
        return result


def set_range(x, y, low, high):
    """
    Parameters
    ----------
    x : array
        independent variable
    y : array
        dependent variable
    low : float
        low bound
    high : float
        high bound

    Returns
    -------
    array :
        x with new range
    array :
        y with new range
    """
    out = np.array([v for v in zip(x, y) if v[0]>low and v[0]<high])
    return out[:,0], out[:,1]




def get_escape_peak(y, ratio, fitting_parameters,
                    escape_e=1.73998):
    """
    Calculate the escape peak for given detector.

    Parameters
    ----------
    y : array
        original spectrum
    ratio : float
        ratio to adjust spectrum
    param : dict

    Returns
    -------
    array:
        x after shift, and adjusted y

    """
    x = np.arange(len(y))

    x = fitting_parameters['e_offset']['value'] + fitting_parameters['e_linear']['value']*x + \
        fitting_parameters['e_quadratic']['value'] * x**2

    return x-escape_e, y*ratio


def get_linear_model(x, param_dict, default_area=1e5):
    """
    Construct linear model for auto fitting analysis.

    Parameters
    ----------
    x : array
        independent variable, channel number instead of energy
    param_dict : dict
        fitting paramters

    Returns
    -------
    e_select : list
        selected elements for given energy
    matv : array
        matrix for linear fitting
    """
    MS = ModelSpectrum(param_dict)
    elist = MS.element_list

    e_select = []
    matv = []

    for i in range(len(elist)):
        e_model = MS.setElementModel(elist[i], default_area=default_area)
        if e_model:
            p = e_model.make_params()
            y_temp = e_model.eval(x=x, params=p)
            matv.append(y_temp)
            e_select.append(elist[i])

    p = MS.compton.make_params()
    y_temp = MS.compton.eval(x=x, params=p)
    matv.append(y_temp)

    p = MS.elastic.make_params()
    y_temp = MS.elastic.eval(x=x, params=p)
    matv.append(y_temp)

    matv = np.array(matv)
    matv = matv.transpose()
    return e_select, matv


class PreFitAnalysis(object):
    """
    It is used to automatic peak finding.
    """
    def __init__(self, experiments, standard):
        self.experiments = np.asarray(experiments)
        self.standard = np.asarray(standard)
        return

    def nnls_fit(self):
        standard = self.standard
        experiments = self.experiments

        [results, residue] = nnls(standard, experiments)

        return results, residue

    def nnls_fit_weight(self):

        standard = self.standard
        experiments = self.experiments

        weights = 1.0 / (1.0 + experiments)
        weights = abs(weights)
        weights = weights/max(weights)

        a = np.transpose(np.multiply(np.transpose(standard),np.sqrt(weights)))
        b = np.multiply(experiments,np.sqrt(weights))

        [results, residue] = nnls(a, b)

        return results, residue
