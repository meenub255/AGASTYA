import io
import contextvars
import pandas as pd
from fastapi.responses import StreamingResponse

export_format_var = contextvars.ContextVar("export_format", default="excel")

def json_to_csv_streaming_response(data: list[dict], filename: str) -> StreamingResponse:
    """
    Converts a list of dictionaries to a CSV file and returns a StreamingResponse.
    """
    df = pd.DataFrame(data)
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    bytes_buffer = io.BytesIO(buffer.getvalue().encode('utf-8'))
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        bytes_buffer,
        media_type='text/csv',
        headers=headers
    )

def json_to_excel_streaming_response(data: list[dict], filename: str) -> StreamingResponse:
    """
    Converts a list of dictionaries to an Excel file (or CSV if format var is set) and returns a StreamingResponse.
    """
    fmt = export_format_var.get()
    if fmt == "csv":
        csv_filename = filename.rsplit('.', 1)[0] + '.csv' if '.' in filename else f"{filename}.csv"
        return json_to_csv_streaming_response(data, csv_filename)

    df = pd.DataFrame(data)
    
    # Create an in-memory buffer
    buffer = io.BytesIO()
    
    # Write the DataFrame to the buffer as an Excel file
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Report')
    
    # Reset buffer position to the beginning
    buffer.seek(0)
    
    # Create the streaming response
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        buffer, 
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )
