/**
 * Created by M. A. Ruberto on 2/28/14.
 */
$(document).ready(function(){
  $('#contents').dataTable( {
    "aaData": history_data,
	"sDom": 'T<"clear">lfrtip',
	"oTableTools": {
					"sSwfPath": "/vmi/static/src/js/datatables/extras/TableTools/media/swf/copy_csv_xls_pdf.swf"
					},
     "aoColumns":[
         {"mData": "date"},
         {"mData": "id"},
         {"mData": "origin"},
         {"mData": "purchase_id"},
         {"mData": "state"}
     ]
} );
});
