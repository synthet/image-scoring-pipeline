const Firebird = require('node-firebird');
const path = require('path');

// Simulate the path logic
const dbPath = path.resolve(path.join(__dirname, '../SCORING_HISTORY.FDB'));
console.log('Resolved DB Path:', dbPath);

const options = {
    host: '127.0.0.1',
    port: 3050,
    database: dbPath,
    user: 'sysdba',
    password: 'masterkey',
    lowercase_keys: true,
    role: ''
};

console.log('Attempting connection...');

Firebird.attach(options, (err, db) => {
    if (err) {
        console.error('Connection Failed!');
        console.error('Error:', err);
        if (err.gdscode) console.error('GDS Code:', err.gdscode);
        return;
    }
    console.log('Connected successfully!');
    db.query('SELECT COUNT(*) FROM IMAGES', (err, result) => {
        if (err) console.error('Query Error:', err);
        else console.log('Result:', result);
        db.detach();
    });
});
