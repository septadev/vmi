/**
 * Created by axll on 10/24/2014.
 */

$(document).ready(function(){
    sessionid = sessionStorage.getItem('session_id');
    pid = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    console.log('before re-authentication: ' + sessionid );

    var anOpen = [];
    var oTable = $('#contents').dataTable( {
    "aaData": invoice_data,
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
         {"mData": "date_invoice"},
         {"mData": "name"},
         {"mData": "amount_untaxed"},
         {"mData": "amount_tax"},
         {"mData": "amount_total"},
         {"mData": function (source, type, val){
             var state = source.state;
             var result;
             switch (state) {
                 case "manager_approved":
                     result = "Septa Manager Approved";
                     break;
                 case "vendor_approved":
                     result = "Vendor Approved";
                     break;
                 case "paid":
                     result = "Septa Paid";
                     break;
                 case "cancel":
                     result = "Cancelled";
                     break;
             }
             return result
         }
         },
         /*{
             "mData": null,
             "sDefaultContent": '<input type="image" class="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png"> ' +
                 '<input type="image" class="denied" title="Deny" src="/vmi/static/src/img/gtk-no.png" style="margin-left: 30px">'
         }*/
         {
             "mData": null,
             "mRender": function (data, type, full){
                 var html = '';
                 if (full["state"] == "manager_approved"){
                     var html =
                     '<form class="respond" id="respond" action="/vmi/invoice_processing" method="post" enctype="multipart/form-data">' +
                         '<input name="callback" value="debug" type="hidden">' +
                         '<input name="uid" value="' + uid + '" type="hidden">' +
                         '<input name="pid" value="' + pid + '" type="hidden">' +
                         '<input name="session_id" value="' + sessionid + '" type="hidden">' +
                         '<input name="invoice_id" value="' + full["id"] + '" type="hidden">' +
                         //'<input id="comment" name="comment" type="hidden">' +
                         //'<input type="image" name="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png" alt="Submit">' +
                         //'<input type="image" name="denied" title="Deny" src="/vmi/static/src/img/gtk-no.png" alt="Submit" style="margin-left: 30px">'
                         '<button type="submit" class="approved" name="result" value="approved" title="Approve"><img title="Approve" src="/vmi/static/src/img/gtk-yes.png"></button>' +
                         '<button type="submit" class="denied" name="result" value="denied" title="Deny"><img title="Deny" src="/vmi/static/src/img/gtk-no.png"></button>' +
                     '</form>';
                     /*function invoiceMessage(){
                         var message = prompt("Please enter the comment regarding this invoice:");
                         if (message != null){
                         $("#comment").val(message);
                         }
                     }*/
                 }
                 return html;
             }
             /*"fnCreatedCell": function(nTd, sData, oData, iRow, iCol){
                 $(".approved", nTd).click(function(){
                     //alert("here")
                     var state = oData["state"];
                     console.log(oData);
                     alert(state);
                     oData["state"] = "vendor_approve";
                     console.log(oData);
                     alert(state);
                 })
             }*/


         }
         /*{
             "aTargets": [6],
             "fnCreatedCell" : function(nTd, sData, oData, iRow, iCol) {
                 var a = $('<input type="image" class="approved" title="Approve" src="/vmi/static/src/img/gtk-yes.png"> ');
                 a.button();
             }
         }*/
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

    /*$("form").submit(function(){
        var message = $("#comment").val();
        alert(message);
        message = prompt("Please enter the comment regarding this invoice:");
        if (message != null){
            $("#comment").val(message);
        }
        alert($("#comment").val());
    });*/
    $(".denied").click(function(){
        $("form").submit(function(){
            var message = prompt("Please enter the comment regarding this invoice:");
            if (message != null){
                var app = '<input name="comment" value="' + message + '" type="hidden">'
                $("form").append(app);
            }
        });
        //$(this).attr("type", "submit");
    });
    $(".approved").click(function(){
        $("form").submit(function(){
            var app = '<input name="comment" value="" type="hidden">'
            $("form").append(app);
        });
    });

function fnFormatDetails (oTable, nTr )
{

    var aData = oTable.fnGetData( nTr );
    var classRow = 'detailRow';
    var sOut = '<div class="innerDetails"><table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">';
    sOut += '<tr class="detailHead"><td>Product ID</td>';
    sOut += '<td>Quantity</td>';
    sOut += '<td>Price Unit</td>';
    sOut += '<td>Discount</td>';
    sOut += '<td>Price Subtotal</td>';
    for(var i in aData.line_items){
        console.log(i);
        /*if(aData.line_items[i].audit_fail == true){
            classRow = 'badAudit'
        }else{
            classRow = 'detailRow'
        }*/
        if(i % 2 == 0){
            classRow = 'detailRowOdd'
        }
        sOut += '<tr class="'+classRow+'"><td>'+aData.line_items[i].product_id+'</td>';
        sOut += '<td>'+aData.line_items[i].quantity+'</td>';
        sOut += '<td>'+aData.line_items[i].price_unit+'</td>';
        sOut += '<td>'+aData.line_items[i].discount+'</td>';
        sOut += '<td>'+aData.line_items[i].price_subtotal+'</td>';
    }
    sOut += '</table></div>';

    return sOut;
}
});