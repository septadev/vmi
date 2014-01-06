# -*- encoding: utf-8 -*-

import glob
import itertools
import json
import operator
import os
import cStringIO
import urllib
import urllib2
import xmlrpclib
import zlib
import simplejson
import base64
import logging
from xml.etree import ElementTree
from simpletal import simpleTAL, simpleTALES
import werkzeug.utils
import werkzeug.wrappers
import openerp
from openerp.tools.translate import _
import openerp.addons.web.http as vmiweb


class VmiController(vmiweb.Controller):
    _cp_path = '/vmi'

    @vmiweb.httprequest
    def index(self, req, mod=None, **kwargs):
        js = """

$(document).ready(function(){
	$("form#loginForm").submit(function() { // loginForm is submitted
	var username = $('#username').attr('value'); // get username
	var password = $('#password').attr('value'); // get password


	if (username && password) { // values are not empty
		$.ajax({
		type: "POST",
		url: "/vmi/client/session/authenticate", // URL of OpenERP Authentication Handler
		contentType: "application/json; charset=utf-8",
		dataType: "json",
		// send username and password as parameters to OpenERP
		data:	 '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": null, "context": {}, "login": "' + username + '", "password": "' + password + '", "db": "dev_main"}, "id": "VMI"}',
		// script call was *not* successful
		error: function(XMLHttpRequest, textStatus, errorThrown) {
			$('div#loginResult').text("responseText: " + XMLHttpRequest.responseText
			+ ", textStatus: " + textStatus
			+ ", errorThrown: " + errorThrown);
			$('div#loginResult').addClass("error");
		}, // error
		// script call was successful
		// data contains the JSON values returned by OpenERP
		success: function(data){
			if (data.result.error) { // script returned error
			$('div#loginResult').text("data.result.title: " + data.result.error);
			$('div#loginResult').addClass("error");
			} // if
			else { // login was successful
			$('form#loginForm').hide();
			$('div#loginResult').html("<h2>Success!</h2> "
				+ " Welcome <b>" + data.result.company + "</b>");
			$('div#loginResult').addClass("success");
			responseData = data.result;
			sessionid = data.result.session_id;
			$('div#vmi_menu').fadeIn();
			} //else
		} // success
		}); // ajax
	} // if
	else {
		$('div#loginResult').text("enter username and password");
		$('div#loginResult').addClass("error");
	} // else
	$('div#loginResult').fadeIn();
	return false;
	});
});

		"""
        input = open(
            '/home/amir/dev/parts/openerp-7.0-20131118-002448/openerp/addons/vmi/vmi_web/template/index.html', 'r')
        template = simpleTAL.compileHTMLTemplate(input)
        input.close()

        context = simpleTALES.Context()
        # Add a string to the context under the variable title
        context.addGlobal("title", "SEPTA VMI Client")
        context.addGlobal("script", js)

        output = cStringIO.StringIO()
        template.expand(context, output)
        return output.getvalue()
