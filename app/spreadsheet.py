import boto3
from botocore.exceptions import ClientError
import os
import xlsxwriter


def create_workbook(filename):
    return xlsxwriter.Workbook(filename)


def add_resource_worksheet_to_workbook(workbook, resources, resource_name):
    worksheet = workbook.add_worksheet(resource_name)
    resource_header = resources[0].to_header()

    # create header in worksheet
    bold_format = workbook.add_format({'bold': True, "align": "left", "font_size": 15})
    standard_format = workbook.add_format({"font_size": 12, 'align': 'left'})
    worksheet.write_row(0, 0, resource_header, bold_format)

    # widen the columns for readability
    worksheet.set_column(0, len(resource_header)+1, 20)

    # Write resources data to worksheet
    col_num = 1
    for resource in resources:
        resource_data = resource.to_list()
        # convert any lists in resource_data from list to formatted string
        resource_data = [", ".join(data) if type(data) is list else data for data in resource_data]
        worksheet.write_row(col_num, 0, resource_data, standard_format)
        col_num += 1
    return workbook


def upload_spreadsheet_to_s3(filename, workbook):
    # save the workbook to the cwd by closing
    workbook.close()

    # Upload the file to S3
    s3_client = boto3.client('s3')
    bucket = "nagbot-spreadhseets"
    try:
        # response = s3_client.upload_file(file_name, bucket, object_name)
        s3_client.upload_file(filename, bucket, filename)
    except ClientError as e:
        print(e)

    # Cleanup and delete the workbook
    os.remove(filename)
