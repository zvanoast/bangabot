FROM gorialis/discord.py

WORKDIR /app

# Set Python to run in unbuffered mode, which ensures logs get output immediately
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Use the -u flag to run Python in unbuffered mode (extra assurance for log output)
CMD ["python", "-u", "main.py"]