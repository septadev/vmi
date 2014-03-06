/**
 * Created by M. A. Ruberto on 2/28/14.
 */

/* Formating function for row details */




$(document).ready(function(){
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
     ]
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
function fnFormatDetails ( nTr )
{
    var aData = oTable.fnGetData( nTr );
    var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
    sOut += '<tr><td>SEPTA P/N</td><td>'+aData.line_items[0].product_details[0].default_code+'</td></tr>';
    sOut += '<tr><td>Quantity</td><td>'+aData.line_items[0].product_qty+'</td></tr>';
    sOut += '<tr><td>U of M</td><td>'+aData.line_items[0].product_uom[1]+'</td></tr>';
    sOut += '<tr><td>Discrepency</td><td>'+aData.line_items[0].audit_fail+'</td></tr>';
    sOut += '<tr><td>Category</td><td>'+aData.line_items[0].product_details[0].categ_id[1]+'</td></tr>';
    sOut += '<tr><td>Location</td><td>'+aData.line_items[0].location_dest_id[1]+'</td></tr>';
    sOut += '<tr><td>Vendor P/N</td><td>'+aData.line_items[0].product_details[0].vendor_part_number+'</td></tr>';
    sOut += '<tr><td>Description</td><td>'+aData.line_items[0].product_details[0].description+'</td></tr>';
    sOut += '</table></div>';

    return sOut;
}
});

