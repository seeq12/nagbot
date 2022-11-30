import boto3
from botocore.exceptions import ClientError
import os
import xlsxwriter
import tempfile


def create_workbook(filename: str) -> object:
    return xlsxwriter.Workbook(filename)


def add_worksheet_to_workbook(workbook: object, resources: list, resource_name: str) -> object:
    worksheet = workbook.add_worksheet(resource_name)

    table_data = []
    # Write resources data to worksheet
    for col_num, resource in enumerate(resources):
        resource_data = resource.to_list()
        # convert any lists in resource_data from list to formatted string
        resource_data = [", ".join(data) if type(data) is list else data for data in resource_data]
        table_data.append(resource_data)
        worksheet.write_row(col_num+1, 0, resource_data)
        # add hyperlink to id column
        worksheet.write_url(col_num+1, 0, resource.get_resource_url(), string=resource.resource_id)

    headers = [{"header": header} for header in resources[0].to_header()]

    worksheet.add_table(0, 0, len(resources), len(headers)-1, {'columns': headers})

    # Format column width of the worksheet to be slightly bigger than the
    # longest string in each column, starting with the column header
    for col_num in range(len(headers)):
        max_col_width = 0
        if len(headers[col_num]["header"]) > max_col_width:
            max_col_width = len(headers[col_num]["header"])
        for data in table_data:
            if len(str(data[col_num])) > max_col_width:
                max_col_width = len(str(data[col_num]))
        worksheet.set_column(col_num, col_num, max_col_width+2)

    return workbook


def add_summary_worksheet_to_workbook(workbook: object, total_resource_cost_dict: dict) -> object:
    worksheet = workbook.add_worksheet("Summary")
    bold = workbook.add_format({'bold': True})
    worksheet.write(1, 0, "Total Cost", bold)
    for col_num, resource in enumerate(total_resource_cost_dict):
        worksheet.write(0, col_num+1, resource, bold)
        worksheet.write(1, col_num+1, total_resource_cost_dict[resource])
    worksheet.set_column(0, 5, 10)
    # set summary worksheet as the first visible sheet in the workbook
    worksheet.activate()
    return workbook


# Uploads the spreadsheet to s3 bucket, and returns the bucket url
def upload_spreadsheet_to_s3(filename: str, workbook: object) -> str:
    cwd = os.getcwd()
    bucket = "nagbot-spreadsheets"

    try:
        # save the workbook to a temporary directory
        temp_directory = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.chdir(temp_directory.name)
        workbook.close()
        # Upload the spreadsheet to S3
        s3_client = boto3.client('s3')
        try:
            s3_client.upload_file(filename, bucket, filename)
        except ClientError as e:
            print(e)

    finally:
        os.chdir(cwd)
        temp_directory.cleanup()

    return f"https://s3.console.aws.amazon.com/s3/buckets/{bucket}?prefix={filename}"


def get_col_widths(worksheet: object) -> list:
    # First we find the maximum length of the index column
    idx_max = max([len(str(s)) for s in worksheet.index.values] + [len(str(worksheet.index.name))])
    # Then, we concatenate this to the max of the lengths of column name and its values for each column, left to right
    return [idx_max] + [max([len(str(s)) for s in worksheet[col].values] + [len(col)]) for col in worksheet.columns]
