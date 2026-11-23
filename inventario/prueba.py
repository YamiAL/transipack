from dbfpy3 import dbf

## create empty DBF, set fields



# db = dbf.Dbf("test.dbf", new=True)
# db.add_field("name",'C',80)
# # db.add_field(
# #     ("NAME", "C", 15),
# #     ("SURNAME", "C", 25),
# #     ("INITIALS", "C", 10),
# #     ("BIRTHDATE", "D"),
# # )
# db.close()
# from dbf import *

# def demo2():
#     dbfn=dbf_new()
   
#     dbfn.add_field("name",'C',80)
#     dbfn.add_field("price",'N',10,2)
#     dbfn.add_field("date",'D',8)
#     dbfn.write("D:\\tst.dbf")
#     # test new dbf
#     print ("*** created tst.dbf: ***")
#     # dbft = Dbf()
#     # dbft.openFile('tst.dbf', readOnly=0)
#     # dbft.reportOn()
   
#     # # add a record
#     # rec=DbfRecord(dbft)
#     # rec['name']='something'
#     # rec['price']=10.5
#     # rec['date']=(2000,1,12)
#     # rec.store()
#     # # add another record
#     # rec=DbfRecord(dbft)
#     # rec['name']='foo and bar'
#     # rec['price']=12234
#     # rec['date']=(1992,7,15)
#     # rec.store()
#     dbft.close()

# def demo1():
#     dbf1 = Dbf()
#     dbf1.openFile('county.dbf', readOnly=1)

#     dbf1.reportOn()
#     print ('sample records:')
#     for i1 in range(min(3,len(dbf1))):
#         rec = dbf1[i1]
#         for fldName in dbf1.fieldNames():
#             print ('%s:\t %s'%(fldName, rec[fldName]))
#         print()
#     dbf1.close()
# **************************************
# filename = 'county.dbf'
# dbfa = dbf.Dbf(filename, new=True)
# dbfa.addField(
#     ("NAME", "C", 15),
#     ("SURNAME", "C", 25),
#     ("INITIALS", "C", 10),
#     ("BIRTHDATE", "D"),
# )
# for (n, s, i, b) in (
#     ("John", "Miller", "YC", (1980, 10, 11)),
#     ("Andy", "Larkin", "", (1980, 4, 11)),
# ):
#     rec = dbfa.newRecord()
#     rec["NAME"] = n
#     rec["SURNAME"] = s
#     rec["INITIALS"] = i
#     rec["BIRTHDATE"] = b
#     rec.store()
# dbfa.close()
# ******************************************

import dbf

# db = dbf("test.dbf", new=True)
table = dbf.Table('temptable.dbf', 'name C(30); age N(3,0); birth D')

print('db definition created with field names:', table.field_names)

table.open(mode=dbf.READ_WRITE)
for datum in (('John Doe', 31, dbf.Date(1979, 9,13)),('Ethan Furman', 102, dbf.Date(1909, 4, 1)),('Jane Smith', 57, dbf.Date(1954, 7, 2)),('John Adams', 44, dbf.Date(1967, 1, 9)),):
    table.append(datum)

print ('records added:')
for record in table:
    print (record)
    print ('-----')

table.close()

table.open(mode=dbf.READ_WRITE)

table.add_fields('telephone C(10)')

telephones = {'John Doe': '1234', 'Ethan Furman': '2345', 'Jane Smith': '3456', 'John Adams': '4567'}
for record in table:
    with record as r:
        r.telephone = telephones[r.name.strip()]

print ('updated records')
for record in table:
    print (record)
    print ('-----')


