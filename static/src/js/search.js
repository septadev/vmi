/**
 * Created by think on 4/4/14.
 */
/**
 * Created by M. A. Ruberto on 2/28/14.
 */

/* Formatting function for row details */




$(document).ready(function(){
    var anOpen = [];
    var oTable = $('#contents').dataTable( {
    "aaData": search_result,
	"sDom": 'T<"clear">lfrtip',
	"oTableTools": {
					"sSwfPath": "/vmi/static/src/js/datatables/extras/TableTools/media/swf/copy_csv_xls_pdf.swf"
					},
     "aoColumns":[
         {"mData": "default_code"},
         {"mData": "vendor_part_number"},
         {"mData": "name"},
         {"mData": "categ_id"},
         {"mData": "uom_id"}
     ],
     "sPaginationType":"full_numbers"
} );


});

