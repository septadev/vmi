/**
 * Created by M. A. Ruberto on 2/28/14.
 */

/* Formating function for row details */

//var sessionid = null;

$(document).ready(function(){
    sessionid = sessionStorage.getItem('session_id');
    pid = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    console.log('before re-authentication: ' + sessionid );

    //authenticate();
    var anOpen = [];
    var oTable = $('#contents').dataTable( {
    "aaData": history_data,
	"sDom": 'T<"clear">lfrtip',
	"oTableTools": {
					"sSwfPath": "/vmi/static/src/js/datatables/extras/TableTools/media/swf/copy_csv_xls_pdf.swf"
					},
     "aoColumns":[
         {
               "mDataProp": null,
               "sClass": "control center",
               "sDefaultContent": '<img src="/vmi/static/src/img/details_open.png">'
         },
         {"mData": "date"},
         {"mData": "origin"},
         {"mData": "purchase_id"},
         {"mData": "state"}
     ],
     "sPaginationType":"full_numbers"
} );
  $('#contents td.control').live( 'click', function () {
  var nTr = this.parentNode;
  var i = $.inArray( nTr, anOpen );

  if ( i === -1 ) {
    $('img', this).attr( 'src', "/vmi/static/src/img/details_close.png" );
    var nDetailsRow = oTable.fnOpen( nTr, fnFormatDetails(oTable, nTr), 'details' );
    $('div.innerDetails', nDetailsRow).slideDown();
    anOpen.push( nTr );
  }
  else {
    $('img', this).attr( 'src', "/vmi/static/src/img/details_open.png" );
    $('div.innerDetails', $(nTr).next()[0]).slideUp( function () {
      oTable.fnClose( nTr );
      anOpen.splice( i, 1 );
    } );
  }
} );
function fnFormatDetails (oTable, nTr )
{

    var aData = oTable.fnGetData( nTr );
    var classRow = 'detailRow';
    var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
    sOut += '<tr class="detailHead"><td>SEPTA P/N</td>';
    sOut += '<td>Quantity</td>';
    sOut += '<td>U of M</td>';
    sOut += '<td>Discrepency</td>';
    sOut += '<td>Category</td>';
    sOut += '<td>Location</td>';
    sOut += '<td>Vendor P/N</td>';
    sOut += '<td>Description</td></tr>\n';
    for(var i in aData.line_items){
        console.log(i);
        if(aData.line_items[i].audit_fail == true){
            classRow = 'badAudit'
        }else{
            classRow = 'detailRow'
        }
        if(i % 2 == 0){
            classRow = 'detailRowOdd'
        }
        sOut += '<tr class="'+classRow+'"><td>'+aData.line_items[i].product_details[0].default_code+'</td>';
        sOut += '<td>'+aData.line_items[i].product_qty+'</td>';
        sOut += '<td>'+aData.line_items[i].product_uom[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].audit_fail+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].categ_id[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].location_dest_id[1]+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].vendor_part_number+'</td>';
        sOut += '<td>'+aData.line_items[i].product_details[0].description+'</td></tr>\n';
    }
    sOut += '</table></div>';

    return sOut;
}

function authenticate(){
    var username = sessionStorage.getItem('username');
    var password = sessionStorage.getItem('password');
    getSessionInfo();
	if (username && password) { // values are not empty

		$.ajax({
		type: "POST",
		url: "/vmi/session/authenticate", // URL of OpenERP Authentication Handler
		contentType: "application/json; charset=utf-8",
		dataType: "json",
		// send username and password as parameters to OpenERP
		data:	 '{"jsonrpc": "2.0", "method": "call", "params": {"session_id": "' + sessionid + '", "context": {}, "login": "' + username + '", "password": "' + password + '", "db": "alpha"}, "id": "VMI"}',
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
			//sessionid = data.result.session_id;
			sessionStorage.setItem("user_id", data.result.uid);
			sessionStorage.setItem("session_id", sessionid);
			/*$('a').each(function()
            {
             var href = $(this).attr('href');
             href += (href.match(/\?/) ? '&' : '?') + 'session_id=' + sessionid;
             $(this).attr('href', href);
            });*/
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
}

function getSessionInfo(){
  $.ajax({
	type: "POST",
	url: "/vmi/session/get_session_info", // URL of OpenERP Handler
	contentType: "application/json; charset=utf-8",
	dataType: "json",
	data: '{"jsonrpc":"2.0","method":"call","params":{"session_id":' + sessionid + ', "context": {}},"id":""}',
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
});

