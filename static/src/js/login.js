/**
 * Created by axll on 2/12/2015.
 */
$(document).ready(function(){
    getSessionInfo();
    $("form#loginForm").submit(function() { // loginForm is submitted
        var username = $('#username').attr('value'); // get username
        var password = $('#password').attr('value'); // get password
        sessionStorage.setItem('username', username);
        sessionStorage.setItem('password', password);

        if (username && password) { // values are not empty
            $.ajax({
                type: "POST",
                url: "/vmi/session/authenticate", // URL of OpenERP Authentication Handler
                contentType: "application/json; charset=utf-8",
                dataType: "json",
                // send username and password as parameters to OpenERP
                data: '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": "' + sessionid + '", "context": {}, "login": "' + username + '", "password": "' + password + '"}, "id": "VMI"}',
                // script call was *not* successful
                error: function (XMLHttpRequest, textStatus, errorThrown) {
                    $('div#loginError').html("responseText: " + XMLHttpRequest.responseText
                        + ", textStatus: " + textStatus
                        + ", errorThrown: " + errorThrown);
                    $('div#loginError').addClass("error");
                    $('div#loginError').fadeIn();
                }, // error
                // script call was successful
                // data contains the JSON values returned by OpenERP
                success: function (data) {
                    if (data.error) { // script returned error
                        $('div#loginError').html("Server Error");
                        $('div#loginError').addClass("error");
                        $('div#loginError').fadeIn();
                    } // if
                    else if (data.result.code){
                        $('div#loginError').text("Incorrect Username or Password!");
                        $('div#loginError').addClass("error");
                        $('div#loginError').fadeIn();
                    }
                    else{ // login was successful
                        $('form#loginForm').hide();
                        $('div#loginResult').html("<h2>Success!</h2> "
                            + " Welcome <b>" + data.result.company + "</b>");
                        $('div#loginResult').addClass("success");
                        $('#vendor').html("Hi, " + data.result.company);
                        $('div#loginResult').fadeIn();
                        $('div#contactContent').fadeIn();
                        $('div#vendor').fadeIn();
                        responseData = data.result;
                        sessionid = data.result.session_id;
                        partnerid = data.result.partner_id;
                        companyid = data.result.company_id;
                        companyname = data.result.company;
                        sessionStorage.setItem("user_id", data.result.uid);
                        sessionStorage.setItem("session_id", sessionid);
                        sessionStorage.setItem("partner_id", partnerid);
                        sessionStorage.setItem("company_id", companyid);
                        sessionStorage.setItem("company_name", companyname);

                        $('a').each(function () {
                            var href = $(this).attr('href');
                            href += (href.match(/\?/) ? '&' : '?') + 'session_id=' + sessionid + '&company_id=' + companyid;
                            $(this).attr('href', href);
                        });

                        $('div#vmi_menu').fadeIn();
                    } //else
                } // success
            }); // ajax
        } // if
        else {
            $('div#loginResult').text("enter username and password");
            $('div#loginResult').addClass("error");
        } // else
        return false;
    });
    });
function getSessionInfo(){
    $.ajax({
        type: "POST",
        url: "/vmi/session/get_session_info", // URL of OpenERP Handler
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        data: '{"jsonrpc":"2.0","method":"call","params":{"session_id": null, "context": {}},"id":"r0"}',
        // script call was *not* successful
        error: function(XMLHttpRequest, textStatus, errorThrown) {
        }, // error
        // script call was successful
        // data contains the JSON values returned by OpenERP
        success: function(data){
            if (data.result && data.result.error) { // script returned error
                $('div#loginResult').text("Warning: " + data.result.error);
                $('div#loginResult').addClass("notice");
            }
            else if (data.error) { // OpenERP error
                $('div#loginResult').text("Error-Message: " + data.error.message + " | Error-Code: " + data.error.code + " | Error-Type: " + data.error.data.type);
                $('div#loginResult').addClass("error");
            } // if
            else { // successful transaction
                sessionid = data.result.session_id;
                console.log( sessionid );
            } //else
        } // success
    }); // ajax
};