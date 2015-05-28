/**
 * Created by M. A. Ruberto on 2/28/14.
 * Rewrite by Xiang Li
 */

$(document).ready(function(){
    sessionid = sessionStorage.getItem('session_id');
    company_id = sessionStorage.getItem(('company_id'));
    uid = sessionStorage.getItem(('user_id'));
    //Initialize datatable
    var anOpen = [];
    var oTable = $('#contents').dataTable( {
        "aoColumns":[
             {"mData": "default_code"},
             {"mData": "vendor_part_number"},
             {"mData": "name"},
             {"mData": "categ_id.1"},
             {"mData": "uom_id.1"}
        ],
        "sPaginationType":"full_numbers"
    });
    // Function when submit button clicked
    $('#submit_pn').click(function(){
        $.ajax({
            type: "POST",
            url: "/vmi/get_product",
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            data: '{"jsonrpc": "2.0","method":"call","params":{"session_id": "' + sessionid + '",' +
                '"context": {"septa_pn": "' + $('#septa_pn').val() + '", "vendor_pn": "' + $('#vendor_pn').val() + '"}, ' +
                '"company_id": "' + company_id + '"' +
                '},"id":"VMI"}',
            error: function (XMLHttpRequest, textStatus, errorThrown) {
            },
            success: function (data) {
                if (data.result && data.result.error) { // script returned error
                }
                else if (data.error) { // OpenERP error
                } // if
                else { // successful transaction
                    //Display missing parts if exists
                    var output = '';
                    if (data.result.hasOwnProperty('missing_septa_pn')){
                        output += "Missing Septa Part Number: " + data.result['missing_septa_pn'] + '<br>';
                    }
                    if (data.result.hasOwnProperty('missing_vendor_pn')){
                        output += "Missing Vendor Part Number: " + data.result['missing_vendor_pn'] + '<br>';
                    }
                    $('#missing_parts').html(output).css("color", "#ff0000").show();

                    //destroy old table and generate a new one with respond data
                    oTable.fnClearTable(0);
                    oTable.fnAddData(data.result['records']);
                    oTable.fnDraw();
                }
            }
        })
    });

});

