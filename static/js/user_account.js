function redeemTime() {
    const idNumber = "{{ idnumber }}"; // Ensure this is the username or idnumber you want to send

    fetch('/redeem_time', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ idnumber: idNumber }) // Sending the idNumber or username
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            document.getElementById('confirmationMessage').style.display = 'block';
        } else {
            alert('Error redeeming time: ' + data.message + ' (Earned Points: ' + data.earned_points + ')');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Error redeeming time.');
    });
}
