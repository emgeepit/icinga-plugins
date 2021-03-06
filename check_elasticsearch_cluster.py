#!/usr/bin/env python

#################################################################################
#                       check_elasticsearch_cluster.py                          #
#               script to check health of elasticsearch_cluster                 #
#           it is also possible to check a query and set thresholds             #
#                   and you can also analyze top hits                           #
#################################################################################

'''
check_elasticsearch_cluster.py
Copyright (C) 2016  langer.markus@gmail.com

updated for es5 by
Copyright (C) 2017
'''

import sys
import json
import urllib2
import argparse
import ssl

# icinga returncode vars
EXIT_OK = 0
EXIT_WARNING = 1
EXIT_CRITICAL = 2
EXIT_UNKNOWN = 3

# check the health
def health( data_url, ctx=None):
    '''checks the general health of the elastic cluster'''

    if ctx == None:
        request = urllib2.Request(str(data_url) + '_cluster/health')
    else:
        request = urllib2.Request(str(data_url) + '_cluster/health')

    es = json.load(urllib2.urlopen(request))
    perfdata = 'nodes=%s data_nodes=%s active_primary_shards=%s active_shards=%s relocating_shards=%s initializing_shards=%s unassigned_shards=%s' \
    % (es['number_of_nodes'],es['number_of_data_nodes'],es['active_primary_shards'],es['active_shards'],es['relocating_shards'],es['initializing_shards'],es['unassigned_shards'])
    message = ': Cluster: %s. Timed out: %s | %s' % (es['status'], es['timed_out'], perfdata)
    if es["status"] == "red":
        critical_exit(message)
    elif es["status"] == "yellow":
        warning_exit(message)
    elif es["status"] == "green":
        ok_exit(message)

def generateES5SearchString(query,duration,top,field):
    searchstring = '{\
            "query":{\
                "bool":{\
                    "must": [ { \
                        "query_string":{\
                            "analyze_wildcard": true,\
                            "query":"' + query + '"\
                        }\
                    },\
                   { "range":{\
                       "@timestamp":{\
                           "from":"now-' + duration + '",\
                           "to":"now"\
                       }\
                   }\
                        }\
                    ]\
                }\
            },\
            '

    if top:
        searchstring += '"aggs": {\
                "top-tags": {\
                    "terms": {\
                        "field": "' + field + '",\
                        "size":' + str(top) + '\
                    }\
                }\
            },\
            "from":0}'
    else:
        searchstring += '"from":0}'
    return searchstring

def generateNotES5SearchString(query,duration,top,field):
    searchstring = '{\
        "query":{\
            "filtered":{\
                "query":{ \
                    "query_string":{\
                        "query":"' + query + '",\
                        "default_field":"_all"\
                    }\
                },\
                "filter":{\
                    "range":{\
                        "@timestamp":{\
                            "from":"now-' + duration + '",\
                            "to":"now"\
                        }\
                    }\
                }\
            }\
        },\
        '
    if top:
        searchstring += '"aggs": {\
                "top-tags": {\
                    "terms": {\
                        "field": "' + field + '",\
                        "size":' + str(top) + '\
                    }\
                }\
            },\
            "from":0}'
    else:
        searchstring += '"from":0}'
    return searchstring


# check a query
def metric( data_url, index, query, critical, warning, invert, duration, top, field, es5,ctx=None):
    infodata = '\n'

    if es5:
        searchstring = generateES5SearchString(query,duration,top,field)
        requeststring = str(data_url) + str(index) + '/_search?size=0'
    else:
        searchstring = generateNotES5SearchString(query,duration,top,field)
        requeststring = str(data_url) + str(index) + '/_search?search_type=count'

    if ctx == None:
        request = urllib2.Request(requeststring,data=searchstring,headers={'Content-type': 'application/json'})
    else:
        request = urllib2.Request(requeststring,data=searchstring,headers={'Content-type': 'application/json'})

    try:
        query_data = json.load(urllib2.urlopen(request))
    except Exception as ex:
        critical_exit("Error making the query: %s" % ex)

    hits = int(query_data['hits']['total'])
    try:
        for info in query_data['aggregations']['top-tags']['buckets']:
            infodata = infodata + str(field)+' '+ str(info['key']) + ': has ' + str(info['doc_count']) + ' hits \n'
    except:
        infodata = ''
    message = ': "%s" returned %s (over %s) %s| query_hits=%s;%s;%s' % (query, hits, duration, infodata, hits, warning or '', critical or '')

    if invert:
        if hits < critical:
            critical_exit(message)
        if hits < warning:
            warning_exit(message)
    else:
        if hits > critical:
            critical_exit(message)
        if hits > warning:
            warning_exit(message)
    ok_exit(message)

# icinga returncode functions
def critical_exit(message):
    '''returns icinga critical'''
    print 'CRITICAL %s' % message
    sys.exit(EXIT_CRITICAL)

def warning_exit(message):
    '''returns icinga warning'''
    print 'WARNING %s' % message
    sys.exit(EXIT_WARNING)

def ok_exit(message):
    '''returns icinga ok'''
    print 'OK %s' % message
    sys.exit(EXIT_OK)

def unknown_exit(message):
    '''returns icinga unknown'''
    print 'UNKNOWN %s' % message
    sys.exit(EXIT_UNKNOWN)

if __name__ == '__main__':
    # request parameters for script
    parser = argparse.ArgumentParser('Icinga check for elasticsearch')
    parser.add_argument('--host', required=True, help='elasticsearch host')
    parser.add_argument('--port', type=int, default=9200, help='port that elasticsearch is running on (eg. 9200)')
    parser.add_argument('--es5', action='store_true', help='Generate ElasticSearch 5 compatible Requests')
    parser.add_argument('--ssl', action='store_true', help='Connect using HTTPS')
    parser.add_argument('--ssl-insecure', action='store_true', help='Do not verify HTTPS cert')
    parser.add_argument('--ssl-cert', help='client cert for HTTPS auth')
    parser.add_argument('--ssl-key', help='client key for HTTPS auth')
    parser.add_argument('--uri', default='', help='Uri for elasticsearch for example /elasticsearch')
    parser.add_argument('--command', default='health', choices=['health','metric'], help='check command')
    parser.add_argument('--index', default='logstash-*', help='the index you want to query for example logstash-*')
    parser.add_argument('--query', help='e.g: source:localhorst AND message:login failed')
    parser.add_argument('--critical', type=int, help='Critical threshold, e.g. 1, 100')
    parser.add_argument('--warning', type=int, help='Warning threshold, e.g. 1, 20')
    parser.add_argument('--invert', action='store_true', help='Invert the check so that an alert is triggered if the value falls below the threshold. Invert is implied if warning threshold > critical threshold')
    parser.add_argument('--duration', default='5m', help='e.g: 1h, 15m, 32d')
    parser.add_argument('--top', help='Display top hits for query')
    parser.add_argument('--field', help='Name of the field you want to have in your top analysis')
    args = parser.parse_args()

    es5 = False
    if args.es5:
        es5 = True

    scheme = "http://"
    if args.ssl or args.ssl_cert or args.ssl_key:
        scheme = "https://"

    try:
        ctx = ssl.create_default_context()
        if args.ssl_insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

    except AttributeError:
	pass


    try:
        data_url = scheme + str(args.host) + ":" + str(args.port) + "/" + str(args.uri)
    except:
        print "something went wrong with the url shit"
    # logic to call the right functions
    if args.command=="metric":
	try:
            metric( data_url, args.index, args.query, args.critical, args.warning, args.invert, args.duration, args.top, args.field, es5, ctx)
        except NameError:
            metric( data_url, args.index, args.query, args.critical, args.warning, args.invert, args.duration, args.top, args.field, es5)
    else:
        try:
            health( data_url,ctx)
        except NameError:
            health( data_url)
