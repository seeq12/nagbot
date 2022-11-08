import boto3
from botocore.exceptions import ClientError
import os
import xlsxwriter
import tempfile


def create_workbook(filename):
    return xlsxwriter.Workbook(filename)


def add_worksheet_to_workbook(workbook, resources, resource_name):
    worksheet = workbook.add_worksheet(resource_name)
    resource_header = resources[0].to_header()

    # create header in worksheet
    bold_format = workbook.add_format({'bold': True, "align": "left"})
    standard_format = workbook.add_format({'align': 'left'})
    worksheet.write_row(0, 0, resource_header, bold_format)

    # widen the columns for readability
    worksheet.set_column(0, len(resource_header)+1, 20)

    # Write resources data to worksheet
    for col_num, resource in enumerate(resources):
        resource_data = resource.to_list()
        # convert any lists in resource_data from list to formatted string
        resource_data = [", ".join(data) if type(data) is list else data for data in resource_data]
        worksheet.write_row(col_num+1, 0, resource_data, standard_format)

    return workbook


# Uploads the spreadsheet to s3 bucket, and returns the bucket url
def upload_spreadsheet_to_s3(filename, workbook):
    cwd = os.getcwd()
    # save the workbook to a temporary directory
    temp_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    os.chdir(temp_directory.name)
    workbook.close()

    # Upload the spreadsheet to S3
    s3_client = boto3.client('s3')
    bucket = "nagbot-spreadhseets"
    try:
        s3_client.upload_file(filename, bucket, filename)
    except ClientError as e:
        print(e)

    os.chdir(cwd)
    temp_directory.cleanup()

    return f"https://s3.console.aws.amazon.com/s3/buckets/{bucket}"
