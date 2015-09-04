VMI
===

Vendor Managed Inventory - an OpenERP(Odoo) 7.0 Add-on

This module
## Installation

VMI runs on the OpenERP 7.0 platform.
### Install OpenERP
1. Create a new Virtual Environment
2. Using that virtualenv
3. Install dependence:
 * pip install -r requirements.txt
 * pip install http://download.gna.org/pychart/PyChart-1.39.tar.gz (need to install seperately)
 * pip install http://www.owlfish.com/software/simpleTAL/downloads/SimpleTAL-4.3.tar.gz
4. Install OpenERP

----
### Install VMI. (Please make sure to copy vmi folder to openerp/addon/)
1. Create a new database and login.
2. Enable Technical Features for administrator.
3. Log out then log back in. you can see more options 
4. Update Module List
5. Go to Installed Modules, uncheck “Installed” and search “vmi” on filter bar.
6. Install "VMI" module and the follow up with the set up

----
## Set up the database
An easy way to set up the database is to use the import_data.py script. This script is designed only for setup the database and doesn’t provide much flexibility to update the table or change the field name. Before using it, make sure you have all the csv files ready and placed in the same folder.
CSV file
Each CSV file represents a model or table in database. If there are parent-child fields in the file, you can use ‘Level’ field to adjust the insert the sequence.  An example is:  example.res.partner.csv
Using Script
1. Run python script import_data.py
2. For a new database, you need to clean the demo data before any data importation
3. For an empty database you can use import all option.

----
## Configuration file
Configuration file is in root folder of every instance

### Here are some key fields:
    list_db: disable the ability to return the list of databases
    db_user: specify the database user name
    db_password: specify the database password
    xmlrpc_port: specify the TCP port for the XML-RPC protocol
    logfile: file where the server log will be stored
    addons_path: specify additional addons paths (separated by commas)
    client_db: Database that client can access.
    client_user: Admin username for this database.
    client_password: Admin password for this database. 
    ap_file: file to interact with ap system
    ap_ftp: ip address for ftp server
    ap_ftp_path: path to ftp server
    ap_ftp_username: username for ftp server
    ap_ftp_password: password for ftp server
    
    

