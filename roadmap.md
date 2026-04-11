### Develop in Flask: Write your Flask app locally. To connect to your AI, you will use the Foundry Project Connection String and the Azure AI Projects SDK.
Push to GitHub: Keep your code in your repository as usual.
Create an Azure App Service: * Go to the Azure Portal.
Search for "Web App" and create a new one.
Set the "Runtime stack" to Python (e.g., Python 3.12).

### Connect to GitHub:
In your new Web App, go to the Deployment Center.
Select GitHub as the source and point it to your repository.
Azure will automatically set up a *GitHub Action* that redeploys your site every time you push code.

inside tghis github action set up tghe security protocols from the task.