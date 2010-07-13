from BeautifulSoup import *
from numpy import *
from wordnet import *
from wntools import *
from Cheetah.Template import Template
from getopt import getopt
from datetime import datetime
import feedparser, re, urllib2, httplib, os, sys

feed_list = ['http://finance.yahoo.com/rss/headline?s=%s',
             'http://www.google.com/finance/company_news?q=NASDAQ:%s&output=rss']

# Retrieve text from markup
def get_text_only(soup):
    v = soup.string
    if v == None:
        c = soup.contents
        result_text = ''
        for t in c:
            sub_text = get_text_only(t)
            result_text += sub_text + '\n'
        return result_text
    else:
        return v.strip()

# Removes stop words and filter English words
def filter_words(words):
    stop_words = open('stop_words.txt', 'r').read().split()
    real_words = []
    for word in words:
        try:
            stop_words.index(word)
        except:
            exists = False
            for values in [N,V,ADV,ADJ]:
                try:
                    values[str(word)]
                    exists = True
                except KeyError:
                    pass
            if exists and len(word) > 2 and not str(word).isdigit():
                real_words.append(word)
    return real_words
             
# Split words from string
def separate_words(text):
    splitter = re.compile('\\W*')
    return [s.lower( ) for s in splitter.split(text) if s != '']

# Creates word matrix
def make_matrix(allw, articlew):
    word_vec = []
    # Only take words that are common but not too common
    for w,c in allw.items( ):
        if c > 3 and c < len(articlew) * 0.6:
            word_vec.append(w)
    l1 = [[(word in f and f[word] or 0) for word in word_vec] for f in articlew]
    return l1,word_vec

# Download feeds and parse
def get_article_words(symbol):
    print 'Downloading articles for %s' % symbol.upper()
    all_words = {}
    article_words = []
    article_titles = []
    article_links = []
    articles = []
    ec = 0
    httplib.HTTPConnection.debuglevel = 1
    num_parsed = 0
    num_parse_errors = 0
    try:
        for feed in feed_list:
            f = feedparser.parse(feed % symbol.lower())
            # Loop entries and do requests
            for e in f.entries:
                # Ignore identical articles
                if e.title.lower() in [t.lower() for t in article_titles]: continue 
                if e.link.find('*') != -1:
                    link = e.link.split('*')[1].replace('%3A', ':')
                else:
                    link = e.link
                if link in article_links: continue
                request = urllib2.Request(link)
                opener = urllib2.build_opener(SmartRedirectHandler())  
                try:
                    c = opener.open(request)
                except:
                    print 'Could not open %s' % link
                    continue
                try:
                    soup = BeautifulSoup(c.read())
                except:
                    print 'Error parsing %s' % link
                    num_parse_errors += 1
                    continue
                print 'Parsed %s' % link
                num_parsed += 1
                text = get_text_only(soup)
                words = separate_words(text)
                words = filter_words(words)
                # Loop over every article and save
                article_words.append({})
                article_titles.append(e.title)
                article_links.append(link)
                articles.append({'title': e.title, 'link': e.link, 'date': datetime(*e.updated_parsed[0:5]).strftime('%m/%d/%y %I:%M %p')})
                # Increase the counts for this word in allwords and in articlewords
                for word in words:
                    all_words.setdefault(word, 0)
                    all_words[word] += 1
                    article_words[ec].setdefault(word, 0)
                    article_words[ec][word] += 1
                ec += 1
    except:
        print 'Error downloading articles for %s' % symbol.upper()
        sys.exit(2)
    print '%d links parsed, %d errors' % (num_parsed, num_parse_errors)
    return all_words,article_words,article_titles,articles

# Sums squares of difference between two values
def difcost(a, b):
    dif = 0
    # Loop over every row and column in the matrix
    for i in range(shape(a)[0]):
        for j in range(shape(a)[1]):
            # Add together the differences
            dif += pow(a[i,j] - b[i,j], 2)
    return dif

# Factorize matrix
def factorize(v, pc=10, iter=100):
    print 'Building features'
    ic = shape(v)[0]
    fc = shape(v)[1]
    # Initialize the weight and feature matrices with random values
    w = matrix([[random.random( ) for j in range(pc)] for i in range(ic)])
    h = matrix([[random.random( ) for i in range(fc)] for i in range(pc)])
    # Perform operation a maximum of iter times
    for i in range(iter):
        wh = w * h
        # Calculate the current difference
        cost = difcost(v, wh)
        # Terminate if the matrix has been fully factorized
        if cost == 0: break
        # Update feature matrix
        hn = (transpose(w) * v)
        hd = (transpose(w) * w * h)
        h = matrix(array(h) * array(hn) / array(hd))
        # Update weights matrix
        wn = (v * transpose(h))
        wd = (w * h * transpose(h))
        w = matrix(array(w) * array(wn) / array(wd))
    return w,h

# Render HTML output
def render_features(symbol, w, h, titles, articles, word_vec, src='templates/default.html', out_path=None):
    # Default output path
    if out_path == None:
        out_dir = 'output'
        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        out_path = out_dir + '/' + symbol.lower() + '.html'
    out_file = file(out_path, 'w')
    pc,wc = shape(h)
    top_patterns = [[] for i in range(len(titles))]
    pattern_names = []
    tpl_features = []
    # Loop over all the features
    for i in range(pc):
        slist = []
        # Create a list of words and their weights
        for j in range(wc):
            slist.append((h[i,j], word_vec[j]))
        # Reverse sort the word list
        slist.sort()
        slist.reverse()
        # Get the first 10 words of the feature
        n = [s[1] for s in slist[0:10]]
        pattern_names.append(n)
        # Create a list of articles for this feature
        flist = []
        for j in range(len(titles)):
            # Add the article with its weight
            flist.append((w[j,i], titles[j], articles[j]))
            top_patterns[j].append((w[j,i], i, titles[j]))
        # Reverse sort the list
        flist.sort()
        flist.reverse()
        # Show the top 3 articles for each feature
        d = dict(names=', '.join(n), articles=[])
        for a in flist[0:3]:
            d['articles'].append({
                'weight': a[0], 
                'title': a[1], 
                'link': a[2]['link'], 
                'date': a[2]['date']
            })
        tpl_features.append(d)
    # Write out template
    tmpl_src = file(src, 'r').read()
    tmpl = Template(tmpl_src, searchList=[{
        'symbol': symbol.upper(), 
        'curr_date': datetime.now().strftime('%m/%d/%y %I:%M:%S %p'),
        'num_features': pc,
        'num_articles': len(articles), 
        'features': tpl_features,
        'articles': articles
    }])
    out_file.write(str(tmpl))
    out_file.close()
    print 'Output generated in %s' % out_path
    # Return the pattern names for later use
    return top_patterns,pattern_names

# Handles 301 and 302 redirects
class SmartRedirectHandler(urllib2.HTTPRedirectHandler):     
    def http_error_301(self, req, fp, code, msg, headers):  
        result = urllib2.HTTPRedirectHandler.http_error_301( 
            self, req, fp, code, msg, headers)              
        result.status = code                                 
        return result                                       

    def http_error_302(self, req, fp, code, msg, headers):   
        result = urllib2.HTTPRedirectHandler.http_error_302(
            self, req, fp, code, msg, headers)              
        result.status = code                                
        return result  

# Takes stock symbol as command line argument
def main(argv):
    opts,args = getopt(argv, 's:o:n:i:')
    if len(opts) < 1:
        print 'Usage: gen_features.py -s <symbol> [-o <outputfile>] [-n <numfeatures>] [-i <iterations>]'
        sys.exit(2) 
    num_features = None
    out_file = None
    iterations = None
    for opt,arg in opts:
        if opt == '-s':
            symbol = arg
        elif opt == '-o':
            out_file = arg
        elif opt == '-n':
            num_features = int(arg)
        elif opt == '-i':
            iterations = int(arg)
    allw,artw,artt,articles = get_article_words(symbol)
    word_matrix,word_vec = make_matrix(allw, artw)
    v = matrix(word_matrix)
    kargs = dict(v=v)
    if num_features != None:
        kargs['pc'] = num_features
    if iterations != None:
        kargs['iter'] = iterations
    weights,feat = factorize(**kargs)
    kargs = dict(symbol=symbol, w=weights, h=feat, titles=artt, articles=articles, word_vec=word_vec)
    if out_file != None:
        kargs['out_path'] = out_file
    render_features(**kargs)
        
if __name__ == '__main__':
    main(sys.argv[1:])
