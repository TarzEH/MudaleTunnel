# Load .NET Assemblies for GUI and Credential Management
Add-Type -AssemblyName PresentationFramework

# Function to create a GUI for user and password input
function Show-CredentialPrompt {
    # Create a Window
    $window = New-Object Windows.Window
    $window.Title = "Admin Credentials"
    $window.SizeToContent = "WidthAndHeight"
    $window.WindowStartupLocation = "CenterScreen"
    $window.ResizeMode = "NoResize"

    # Create a Grid
    $grid = New-Object Windows.Controls.Grid
    $grid.Margin = "10"

    # Create Grid Columns
    $grid.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition)) # Username label
    $grid.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition)) # Username textbox
    $grid.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition)) # Password label
    $grid.ColumnDefinitions.Add((New-Object Windows.Controls.ColumnDefinition)) # Password textbox

    # Create Username Label and TextBox
    $labelUser = New-Object Windows.Controls.Label
    $labelUser.Content = "Username:"
    $textboxUser = New-Object Windows.Controls.TextBox
    $textboxUser.Width = 150

    # Create Password Label and PasswordBox
    $labelPass = New-Object Windows.Controls.Label
    $labelPass.Content = "Password:"
    $passwordBox = New-Object Windows.Controls.PasswordBox
    $passwordBox.Width = 150

    # Create OK Button
    $buttonOK = New-Object Windows.Controls.Button
    $buttonOK.Content = "OK"
    $buttonOK.Width = 75
    $buttonOK.IsDefault = $true

    # Button Event Handler for OK Click
    $buttonOK.Add_Click({
        $window.DialogResult = $true
        $window.Close()
    })

    # Add elements to the Grid
    $grid.RowDefinitions.Add((New-Object Windows.Controls.RowDefinition))
    $grid.RowDefinitions.Add((New-Object Windows.Controls.RowDefinition))

    # Add Username and Password in the same row, side by side
    $grid.Children.Add($labelUser) | Out-Null
    [Windows.Controls.Grid]::SetRow($labelUser, 0)
    [Windows.Controls.Grid]::SetColumn($labelUser, 0)
    
    $grid.Children.Add($textboxUser) | Out-Null
    [Windows.Controls.Grid]::SetRow($textboxUser, 0)
    [Windows.Controls.Grid]::SetColumn($textboxUser, 1)

    $grid.Children.Add($labelPass) | Out-Null
    [Windows.Controls.Grid]::SetRow($labelPass, 0)
    [Windows.Controls.Grid]::SetColumn($labelPass, 2)

    $grid.Children.Add($passwordBox) | Out-Null
    [Windows.Controls.Grid]::SetRow($passwordBox, 0)
    [Windows.Controls.Grid]::SetColumn($passwordBox, 3)

    $grid.Children.Add($buttonOK) | Out-Null
    [Windows.Controls.Grid]::SetRow($buttonOK, 1)
    [Windows.Controls.Grid]::SetColumnSpan($buttonOK, 4)
    $buttonOK.HorizontalAlignment = "Center"

    # Set the window content to the grid
    $window.Content = $grid

    # Show the window as a dialog
    if ($window.ShowDialog()) {
        # Return the credentials entered by the user
        return New-Object -TypeName PSCredential -ArgumentList $textboxUser.Text, ($passwordBox.SecurePassword)
    }
    else {
        return $null
    }
}

# Run the Credential Prompt
$adminCred = Show-CredentialPrompt

if ($null -ne $adminCred) {
    # Example: Run another PowerShell script with the admin credentials
    $scriptPath = "C:\path\to\your\script.ps1" # Change to your script path
    Start-Process powershell.exe -Credential $adminCred -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptPath`""
} else {
    Write-Host "No credentials were entered. Exiting..."
}
